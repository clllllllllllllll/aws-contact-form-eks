# AWS Contact Form on EKS

A two-tier contact form project for the take-home assignment. The application will use Flask for the web form, PostgreSQL on Amazon RDS for storage, and Amazon EKS for container orchestration.

## Planned deployment

1. Terraform provisions the AWS network, EKS cluster, RDS database, IAM permissions, and supporting security services.
2. Ansible deploys the Flask application and Kubernetes resources to EKS.
3. A Kubernetes Ingress and the AWS Load Balancer Controller provide an Application Load Balancer for public access.
4. The application reads database credentials from AWS Secrets Manager through an EKS-compatible secrets integration.

Everything will be deployed from a local workstation without manually creating AWS resources in the Console. Detailed prerequisites, deployment commands, verification steps, and teardown instructions will be added as the implementation progresses.

## Status

Repository initialized. Infrastructure and application code are not implemented yet.
