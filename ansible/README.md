# Ansible scaffold

The deploy and teardown playbooks are intentionally guarded. Running either
stops with a clear message until its tasks are implemented.

Planned roles:
- controller/: install the pinned AWS Load Balancer Controller.
- database/: set up the schema and restricted application SQL user.
- app/: deploy the namespace, service account, Deployment, Service, and Ingress.

Use Terraform's non-secret outputs for resource identifiers. Never put a
database password in Ansible variables, templates, or logs.
