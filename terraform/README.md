# Terraform scaffold

This directory contains three separate root modules. None defines AWS resources yet.

- bootstrap/: create the persistent state backend from the workstation.
- foundation/: retain DNS, state, and required evidence resources between demos.
- workload/: disposable VPC, EKS, RDS, IAM, ECR, and application secret metadata.

Use separate state for foundation and workload. Add account/Region guards,
provider version constraints, remote backend configuration, and resource modules
before any apply. Review Singapore costs and teardown first.
