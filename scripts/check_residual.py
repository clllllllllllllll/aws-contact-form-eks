"""Read-only inventory of disposable contact-form AWS resources after teardown."""

import argparse
import json
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ACCOUNT = "203888389134"
REGION = "ap-southeast-1"
PROJECT = "aws-contact-form-eks"
LIFECYCLE = "workload"
DATABASE_ID = "contact-form-postgres"


def pages(client, operation, **arguments):
    return client.get_paginator(operation).paginate(**arguments)


def workload_tags(tags, key="Key", value="Value"):
    mapping = {item[key]: item[value] for item in tags}
    return mapping.get("Project") == PROJECT and mapping.get("Lifecycle") == LIFECYCLE


def has_name_prefix(item, prefix):
    return any(
        tag.get("Key") == "Name" and tag.get("Value", "").startswith(prefix)
        for tag in item.get("Tags", [])
    )


def vpc_inventory(ec2):
    return {
        item["VpcId"]
        for page in pages(ec2, "describe_vpcs")
        for item in page["Vpcs"]
        if any(tag.get("Key") == "Name" and tag.get("Value") == "contact-form-vpc"
               for tag in item.get("Tags", []))
        or workload_tags(item.get("Tags", []))
    }


def nat_inventory(ec2, vpc_ids):
    gateways = [
        item
        for page in pages(ec2, "describe_nat_gateways")
        for item in page["NatGateways"]
        if item["State"] != "deleted"
        and (item.get("VpcId") in vpc_ids or has_name_prefix(item, "contact-form-nat-"))
    ]
    allocation_ids = {
        address["AllocationId"]
        for gateway in gateways
        for address in gateway.get("NatGatewayAddresses", [])
        if "AllocationId" in address
    }
    addresses = [
        item["AllocationId"]
        for item in ec2.describe_addresses()["Addresses"]
        if item["AllocationId"] in allocation_ids
        or has_name_prefix(item, "contact-form-nat-")
        or workload_tags(item.get("Tags", []))
    ]
    return sorted(gateway["NatGatewayId"] for gateway in gateways), sorted(addresses)


def ebs_inventory(ec2):
    filters = [
        {"Name": "tag:Project", "Values": [PROJECT]},
        {"Name": "tag:Lifecycle", "Values": [LIFECYCLE]},
    ]
    volumes = [
        item["VolumeId"]
        for page in pages(ec2, "describe_volumes", Filters=filters)
        for item in page["Volumes"]
        if workload_tags(item["Tags"]) and item["State"] != "deleted"
    ]
    snapshots = [
        item["SnapshotId"]
        for page in pages(ec2, "describe_snapshots", OwnerIds=["self"], Filters=filters)
        for item in page["Snapshots"]
        if workload_tags(item["Tags"])
    ]
    return sorted(volumes), sorted(snapshots)


def rds_automated_backups(rds):
    return sorted((
        {
            "resource_id": item["DbiResourceId"],
            "status": item["Status"],
        }
        for page in pages(rds, "describe_db_instance_automated_backups", Filters=[
            {"Name": "db-instance-id", "Values": [DATABASE_ID]},
        ])
        for item in page["DBInstanceAutomatedBackups"]
        if item["DBInstanceIdentifier"] == DATABASE_ID
    ), key=lambda item: item["resource_id"])


def kms_tags(kms, key_id):
    tags = []
    marker = None
    while True:
        arguments = {"KeyId": key_id}
        if marker:
            arguments["Marker"] = marker
        response = kms.list_resource_tags(**arguments)
        tags.extend(response["Tags"])
        if not response["Truncated"]:
            return tags
        marker = response["NextMarker"]


def kms_inventory(kms):
    keys = []
    marker = None
    while True:
        arguments = {"Marker": marker} if marker else {}
        response = kms.list_keys(**arguments)
        for entry in response["Keys"]:
            metadata = kms.describe_key(KeyId=entry["KeyId"])["KeyMetadata"]
            if metadata["AWSAccountId"] != ACCOUNT or metadata["KeyManager"] != "CUSTOMER":
                continue
            if not workload_tags(kms_tags(kms, entry["KeyId"]), "TagKey", "TagValue"):
                continue
            item = {"arn": metadata["Arn"], "state": metadata["KeyState"]}
            if "DeletionDate" in metadata:
                item["deletion_date"] = metadata["DeletionDate"].isoformat()
            keys.append(item)
        if not response["Truncated"]:
            return sorted(keys, key=lambda item: item["arn"])
        marker = response["NextMarker"]


def collect(session):
    if session.region_name != REGION:
        raise RuntimeError("AWS session is not set to the approved Singapore Region")
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != ACCOUNT or identity["Arn"].endswith(":root"):
        raise RuntimeError("AWS profile does not match the authorized non-root account")

    ec2 = session.client("ec2")
    vpc_ids = vpc_inventory(ec2)
    nat, addresses = nat_inventory(ec2, vpc_ids)
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
    volumes, ebs_snapshots = ebs_inventory(ec2)

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
        if item["DBInstanceIdentifier"] == DATABASE_ID
    ]

    snapshots = [
        item["DBSnapshotIdentifier"]
        for page in pages(rds, "describe_db_snapshots")
        for item in page["DBSnapshots"]
        if item.get("DBInstanceIdentifier") == DATABASE_ID
    ]
    automated_backups = rds_automated_backups(rds)

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
    kms_keys = kms_inventory(session.client("kms"))

    return {
        "vpcs": sorted(vpc_ids),
        "nat_gateways": sorted(nat),
        "elastic_ips": sorted(addresses),
        "worker_and_relay_instances": sorted(instances),
        "ebs_volumes": volumes,
        "ebs_snapshots": ebs_snapshots,
        "eks_clusters": sorted(clusters),
        "rds_instances": sorted(databases),
        "rds_snapshots": sorted(snapshots),
        "rds_automated_backups": automated_backups,
        "load_balancers": sorted(balancers),
        "ecr_repositories": sorted(repositories),
        "application_secrets": sorted(app_secrets),
        "workload_kms_keys": kms_keys,
    }


def classify_resources(collected):
    pending_keys = [
        key for key in collected["workload_kms_keys"] if key["state"] == "PendingDeletion"
    ]
    actionable = dict(collected)
    actionable["workload_kms_keys"] = [
        key for key in collected["workload_kms_keys"] if key["state"] != "PendingDeletion"
    ]
    return actionable, {"workload_kms_keys": pending_keys}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", default=os.environ.get("AWS_PROFILE", "contact-form-deployer"),
    )
    args = parser.parse_args()
    collected = collect(boto3.Session(profile_name=args.profile, region_name=REGION))
    resources, expected_pending_cleanup = classify_resources(collected)
    found = any(resources.values())
    print(json.dumps({
        "account": ACCOUNT,
        "region": REGION,
        "runtime_resources_remaining": found,
        "resources": resources,
        "expected_pending_cleanup": expected_pending_cleanup,
    }, indent=2))
    return 2 if found else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BotoCoreError, ClientError, RuntimeError, KeyError, TypeError, ValueError,
            AttributeError, IndexError) as error:
        print(f"Residual inventory incomplete; do not assume teardown is clean: {error}", file=sys.stderr)
        sys.exit(1)
