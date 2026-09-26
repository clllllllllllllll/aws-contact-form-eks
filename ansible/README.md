# Kubernetes deployment

These playbooks are drafted and pass local syntax checks. They have not yet been run against EKS. The AWS resources and cheelong.xyz certificate must exist before deployment. Use only synthetic submissions.

## Workstation sequence

Activate the existing virtualenv and confirm the intended account. On another workstation, install requirements-workstation.txt and the pinned ansible/requirements.yml collection first:

    cd /home/limch/projects/aws-contact-form-eks
    source /home/limch/.venvs/assignment/bin/activate
    export AWS_PROFILE=contact-form-deployer
    aws sts get-caller-identity --profile "$AWS_PROFILE"

The identity check must show account 203888389134 and a non-root principal. In terminal 1, start the private API tunnel:

    python3 scripts/open_tunnel.py

This reads Terraform's non-secret workload outputs, checks the account, writes .local/kubeconfig with mode 600, and starts a Session Manager port forward through the private relay. The kubeconfig still verifies the original EKS API hostname and its CA. Leave the terminal open.

In terminal 2, verify the tunnel and worker placement, then deploy:

    cd /home/limch/projects/aws-contact-form-eks
    source /home/limch/.venvs/assignment/bin/activate
    export AWS_PROFILE=contact-form-deployer
    export KUBECONFIG="$PWD/.local/kubeconfig"
    kubectl get nodes -L topology.kubernetes.io/zone
    ansible-playbook -i ansible/inventory.ini ansible/deploy.yml

The node command checks that the private API is reachable and both workers are registered. The playbook reads Terraform outputs, reuses or publishes an immutable ECR image, installs the pinned controller chart, runs the restricted database setup Job, deploys two app replicas in different AZs, then applies the Ingress. The controller creates the physical ALB. After it reports an address, the playbook creates the apex Route 53 alias and waits for a verified HTTPS readiness response.

After a submission with a synthetic address such as `demo@example.com`, show the stored row with `ansible-playbook -i ansible/inventory.ini ansible/verify.yml -e demo_email=demo@example.com` while the tunnel remains open. This creates a short-lived readback Job with the setup-role identity, queries only that address inside the VPC, and prints at most five rows. Do not use a real personal address.

A second playbook run must keep the same image digest and database credential when the app source and infrastructure have not changed. The image-specific setup Job is created if absent, reused if complete, and awaited if running. If it reaches terminal failure, the playbook reports only safe Job/pod status, reason and exit-code fields without raw logs, deletes it, recreates it and waits; a failed replacement stops deployment for investigation and can be retried on the next run. The Job has a one-hour TTL, and its setup script preserves the schema, secret and submitted rows across reruns.

## Cleanup before Terraform destroy

Keep the SSM tunnel running. Stop sending form submissions, then run:

    ansible-playbook -i ansible/inventory.ini ansible/teardown.yml
    WORKLOAD_VARS="$PWD/.local/verified-workload.tfvars.json"
    terraform -chdir=terraform/workload plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out=workload-destroy.tfplan
    terraform -chdir=terraform/workload show -no-color workload-destroy.tfplan

The playbook verifies the account, deletes only an alias pointing to this controller-owned ALB, removes the Ingress, and waits for ALB deletion. It then removes the controller and application namespace. Review the Terraform destroy plan before running `terraform -chdir=terraform/workload apply workload-destroy.tfplan`. The saved plan contains the verified version inputs. A full workload destroy intentionally deletes RDS and demo submissions; the state bucket and foundation remain.

The DNS helper saves a non-secret ownership record at .local/alb-alias.json. That record lets cleanup remove this exact alias if the ALB has already disappeared; an unrelated record is rejected. Keep the record on the workstation that deployed the site until cleanup is complete. If ALB deletion does not complete, the playbook stops. Investigate the controller and AWS resource state before destroying EKS or the VPC. After workload destroy, run `python3 scripts/check_residual.py --profile contact-form-deployer`. Exit 0 reports no actionable remnants within the checker's named/tagged Singapore scope; `PendingDeletion` workload KMS keys appear separately in `expected_pending_cleanup`. Exit 2 lists actionable remnants; exit 1 means an inventory call failed. Other accounts/Regions and resources outside its names and tags, including some untagged or manual assets, are outside scope; exit 0 is not a zero-bill claim. See [final cleanup scope](../docs/final-cleanup.md). The cleanup path has not yet been tested live.

## Ownership and security

Terraform owns AWS network rules, IAM roles, EKS, RDS, ECR and secret metadata. Ansible owns the controller release and Kubernetes resources. The app service account can read only its application secret; the setup Job uses a separate role for the master secret and initial database setup. The app service account has no Kubernetes RoleBinding. The controller uses the pre-created ALB security group and must not mutate security groups.

Chart 1.14.0 runs controller image v2.14.1. Both backend security-group management flags are disabled, and the Ingress sets the Terraform security-group ID plus the matching annotation. The Ingress requests a TLS 1.2/1.3 listener and an HTTP-to-HTTPS redirect. The ALB-to-pod hop remains HTTP inside the VPC.
