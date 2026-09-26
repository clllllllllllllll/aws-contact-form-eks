"""Read-only inventory of disposable contact-form AWS resources after teardown."""

import argparse
import json
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ACCOUNT = "203888389134"
REGION = "ap-southeast-1"


def pages(client, operation, **arguments):
    return client.get_paginator(operation).paginate(**arguments)


def collect(session):
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != ACCOUNT or identity["Arn"].endswith(":root"):
        raise RuntimeError("AWS profile does not match the authorized non-root account")

    ec2 = session.client("ec2")
    vpcs = ec2.describe_vpcs(Filters=[
        {"Name": "tag:Name", "Values": ["contact-form-vpc"]},
    ])["Vpcs"]
    vpc_ids = {item["VpcId"] for item in vpcs}

    nat = [
        item["NatGatewayId"]
        for page in pages(ec2, "describe_nat_gateways", Filter=[
            {"Name": "tag:Name", "Values": ["contact-form-nat-*"]},
        ])
        for item in page["NatGateways"]
        if item["State"] not in ("deleted", "failed")
    ]
    addresses = [
        item["AllocationId"]
        for item in ec2.describe_addresses(Filters=[
            {"Name": "tag:Name", "Values": ["contact-form-nat-*"]},
        ])["Addresses"]
    ]
    instances = [
        item["InstanceId"]
        for page in pages(ec2, "describe_instances", Filters=[
            {"Name": "tag:Name", "Values": [
                "contact-form-ssm-relay", "contact-form-eks-worker",
            ]},
            {"Name": "instance-state-name", "Values": [
                "pending", "running", "stopping", "stopped",
            ]},
        ])
        for reservation in page["Reservations"]
        for item in reservation["Instances"]
    ]

    eks = session.client("eks")
    clusters = [
        name
        for page in pages(eks, "list_clusters")
        for name in page["clusters"]
        if name == "contact-form-eks"
    ]

    rds = session.client("rds")
    databases = [
        item["DBInstanceIdentifier"]
        for page in pages(rds, "describe_db_instances")
        for item in page["DBInstances"]
        if item["DBInstanceIdentifier"] == "contact-form-postgres"
    ]

    snapshots = [
        item["DBSnapshotIdentifier"]
        for page in pages(rds, "describe_db_snapshots")
        for item in page["DBSnapshots"]
        if item.get("DBInstanceIdentifier") == "contact-form-postgres"
    ]

    elbv2 = session.client("elbv2")
    balancers = []
    for page in pages(elbv2, "describe_load_balancers"):
        for item in page["LoadBalancers"]:
            if item["VpcId"] in vpc_ids:
                balancers.append(item["LoadBalancerArn"])
                continue
            tags = elbv2.describe_tags(ResourceArns=[item["LoadBalancerArn"]])
            mapping = {
                tag["Key"]: tag["Value"]
                for tag in tags["TagDescriptions"][0]["Tags"]
            }
            if (
                mapping.get("elbv2.k8s.aws/cluster") == "contact-form-eks"
                and mapping.get("ingress.k8s.aws/stack") == "contact-form/contact-form"
            ):
                balancers.append(item["LoadBalancerArn"])

    ecr = session.client("ecr")
    try:
        repositories = [
            item["repositoryArn"]
            for item in ecr.describe_repositories(repositoryNames=["contact-form"])["repositories"]
        ]
    except ecr.exceptions.RepositoryNotFoundException:
        repositories = []

    secrets = session.client("secretsmanager")
    app_secrets = [
        item["ARN"]
        for page in pages(secrets, "list_secrets", IncludePlannedDeletion=True)
        for item in page["SecretList"]
        if item["Name"].startswith("contact-form/app-")
    ]

    return {
        "vpcs": sorted(vpc_ids),
        "nat_gateways": sorted(nat),
        "elastic_ips": sorted(addresses),
        "worker_and_relay_instances": sorted(instances),
        "eks_clusters": sorted(clusters),
        "rds_instances": sorted(databases),
        "rds_snapshots": sorted(snapshots),
        "load_balancers": sorted(balancers),
        "ecr_repositories": sorted(repositories),
        "application_secrets": sorted(app_secrets),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", default=os.environ.get("AWS_PROFILE", "contact-form-deployer"),
    )
    args = parser.parse_args()
    resources = collect(boto3.Session(profile_name=args.profile, region_name=REGION))
    found = any(resources.values())
    print(json.dumps({
        "account": ACCOUNT,
        "region": REGION,
        "runtime_resources_remaining": found,
        "resources": resources,
    }, indent=2))
    return 2 if found else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BotoCoreError, ClientError, RuntimeError, KeyError) as error:
        print(f"Residual inventory incomplete; do not assume teardown is clean: {error}", file=sys.stderr)
        sys.exit(1)
