"""Show active project findings from AWS Foundational Security Best Practices."""

import argparse
from collections import Counter
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ACCOUNT = "203888389134"
REGION = "ap-southeast-1"
PROJECT = "aws-contact-form-eks"
FSBP_ID = "standards/aws-foundational-security-best-practices/v/1.0.0"
PRODUCT_ARN = f"arn:aws:securityhub:{REGION}::product/aws/securityhub"


def is_fsbp(finding):
    compliance = finding.get("Compliance") or {}
    if any(
        standard.get("StandardsId") == FSBP_ID
        for standard in compliance.get("AssociatedStandards", [])
    ):
        return True
    # Standard-specific findings use this field when consolidation is disabled.
    standards_arn = (finding.get("ProductFields") or {}).get("StandardsArn", "")
    return standards_arn.endswith(":" + FSBP_ID)


def has_project_name(service, name, resource_type):
    if service == "eks":
        return name == "cluster/contact-form-eks" or name.startswith((
            "nodegroup/contact-form-eks/", "addon/contact-form-eks/",
        ))
    if service == "rds":
        return name == "db:contact-form-postgres" or name.startswith(
            "snapshot:contact-form-postgres-"
        )
    if service == "secretsmanager":
        return name.startswith("secret:contact-form/app-")
    if service == "ecr":
        return name == "repository/contact-form"
    if service == "s3":
        return name in {
            f"aws-contact-form-eks-tfstate-{ACCOUNT}-{REGION}",
            f"aws-contact-form-evidence-{ACCOUNT}-{REGION}",
        }
    if service == "cloudtrail":
        return name == "trail/contact-form-management"
    if service == "logs":
        return name in {
            "log-group:/aws/eks/contact-form-eks/cluster",
            "log-group:/aws/eks/contact-form-eks/cluster:*",
        } or name.startswith("log-group:/aws/rds/instance/contact-form-postgres/")
    if service == "iam":
        return name.startswith(("role/contact-form-", "instance-profile/contact-form-")) \
            or name in {"user/contact-form-deployer", "group/contact-form-provisioners"}
    if service == "elasticloadbalancing":
        return name.startswith("loadbalancer/app/k8s-contactf-contactf-")
    if service == "" and resource_type == "":
        return name in {
            "contact-form-vpc", "contact-form-igw", "contact-form-alb",
            "contact-form-nodes", "contact-form-rds", "contact-form-relay",
            "contact-form-db", "contact-form-eks-worker",
            "contact-form-eks-worker-root", "contact-form-ssm-relay",
            "contact-form-ssm-relay-root",
        } or name.startswith((
            "contact-form-public-", "contact-form-app-", "contact-form-db-",
            "contact-form-nat-",
        ))
    # Some ASFF resources use a service identifier instead of an ARN.
    return (service == "" and (
        (resource_type == "AwsRdsDbInstance" and name == "contact-form-postgres")
        or (resource_type == "AwsEksCluster" and name == "contact-form-eks")
    ))


def is_project_resource(resource):
    resource_id = resource.get("Id", "")
    if not isinstance(resource_id, str) or not resource_id:
        return False
    service, name = "", resource_id
    if resource_id.startswith("arn:"):
        parts = resource_id.split(":", 5)
        if (len(parts) != 6 or parts[1] != "aws"
                or parts[3] not in ("", REGION)
                or parts[4] not in ("", ACCOUNT)):
            return False
        service, name = parts[2], parts[5]
    tags = resource.get("Tags") or {}
    if isinstance(tags, dict) and tags.get("Project") == PROJECT:
        return True
    if has_project_name(service, name, resource.get("Type", "")):
        return True
    return isinstance(tags, dict) and has_project_name("", tags.get("Name", ""), "")


def project_rows(client):
    filters = {
        "RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}],
        "AwsAccountId": [{"Value": ACCOUNT, "Comparison": "EQUALS"}],
        "ProductArn": [{"Value": PRODUCT_ARN, "Comparison": "EQUALS"}],
    }
    rows = []
    for page in client.get_paginator("get_findings").paginate(Filters=filters):
        for finding in page.get("Findings", []):
            if (finding.get("RecordState") != "ACTIVE"
                    or finding.get("AwsAccountId") != ACCOUNT
                    or finding.get("Region") != REGION
                    or finding.get("ProductArn") != PRODUCT_ARN
                    or not is_fsbp(finding)):
                continue
            compliance = finding.get("Compliance") or {}
            control = compliance.get("SecurityControlId") or (
                finding.get("ProductFields") or {}
            ).get("ControlId") or "-"
            for resource in finding.get("Resources", []):
                if is_project_resource(resource):
                    rows.append((
                        control, compliance.get("Status") or "UNKNOWN",
                        resource["Id"], finding.get("UpdatedAt") or "-",
                    ))
    return sorted(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="contact-form-deployer")
    parser.add_argument("--summary", action="store_true",
                        help="show concise counts and failed control IDs")
    args = parser.parse_args()
    try:
        session = boto3.Session(profile_name=args.profile, region_name=REGION)
        rows = project_rows(session.client("securityhub"))
    except (ClientError, BotoCoreError) as error:
        code = (error.response.get("Error", {}).get("Code", "ClientError")
                if isinstance(error, ClientError) else type(error).__name__)
        parser.exit(1, f"Security Hub read failed ({code}); no findings report produced.\n")

    print(f"ACTIVE FSBP project findings | account {ACCOUNT} | {REGION}")
    if args.summary:
        print(f"Snapshot UTC: {datetime.now(timezone.utc):%Y-%m-%d %H:%M}")
        passed_workload = sorted({
            control for control, status, _, _ in rows
            if status == "PASSED" and control.startswith(("EKS.", "RDS.", "ELB."))
        })
        print("Passing EKS/RDS/ALB controls: "
              + (", ".join(passed_workload) or "none observed"))
        failures = Counter(control for control, status, _, _ in rows
                           if status == "FAILED")
        print("Failed control | Finding count")
        for control, count in sorted(failures.items()):
            print(f"{control} | {count}")
    elif rows:
        print("Control | Status | Resource | UpdatedAt")
        for control, status, resource_id, updated_at in rows:
            print(f"{control} | {status} | {resource_id} | {updated_at}")
    else:
        print("No matching findings observed.")
    counts = Counter(status for _, status, _, _ in rows)
    statuses = ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
    print(f"Summary: {len(rows)} project resource finding(s); {statuses or 'none'}.")
    print("Zero matches do not prove that all controls passed or finished evaluating.")


if __name__ == "__main__":
    main()
