"""Manage the contact form DNS alias and verify ALB cleanup by owner tags."""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "ap-southeast-1"
CLUSTER = "contact-form-eks"
STACK = "contact-form/contact-form"
ACCOUNT = "203888389134"
ALIAS_RECORD_PATH = Path(__file__).resolve().parents[1] / ".local" / "alb-alias.json"


def normalized(name):
    return name.lower().rstrip(".")


def normalized_alb_dns(name):
    return normalized(name).removeprefix("dualstack.")


def read_alias_record():
    if not ALIAS_RECORD_PATH.exists():
        return None
    try:
        return json.loads(ALIAS_RECORD_PATH.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError("The local ALB ownership record is unreadable") from error


def save_alias_record(args, alb):
    payload = {
        "account": ACCOUNT,
        "cluster": CLUSTER,
        "stack": STACK,
        "zone_id": args.zone_id,
        "domain": normalized(args.domain),
        "dns_name": normalized(alb["DNSName"]),
        "alb_zone_id": alb["CanonicalHostedZoneId"],
    }
    directory = ALIAS_RECORD_PATH.parent
    directory.mkdir(mode=0o700, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory,
        prefix=".alb-alias-", delete=False,
    ) as temporary:
        json.dump(payload, temporary, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o600)
    temporary_path.replace(ALIAS_RECORD_PATH)
    ALIAS_RECORD_PATH.chmod(0o600)


def record_matches_alias(args, record):
    marker = read_alias_record()
    target = record.get("AliasTarget", {})
    return bool(
        marker
        and marker.get("account") == ACCOUNT
        and marker.get("cluster") == CLUSTER
        and marker.get("stack") == STACK
        and marker.get("zone_id") == args.zone_id
        and marker.get("domain") == normalized(args.domain)
        and normalized_alb_dns(marker.get("dns_name", "")) == normalized_alb_dns(target.get("DNSName", ""))
        and marker.get("alb_zone_id") == target.get("HostedZoneId")
    )


def clear_alias_record(args):
    marker = read_alias_record()
    if (
        marker
        and marker.get("zone_id") == args.zone_id
        and marker.get("domain") == normalized(args.domain)
    ):
        ALIAS_RECORD_PATH.unlink()


def owned_balancers(client):
    paginator = client.get_paginator("describe_load_balancers")
    for page in paginator.paginate():
        balancers = page["LoadBalancers"]
        for start in range(0, len(balancers), 20):
            chunk = balancers[start:start + 20]
            try:
                tag_descriptions = client.describe_tags(
                    ResourceArns=[item["LoadBalancerArn"] for item in chunk],
                )["TagDescriptions"]
            except ClientError as error:
                if error.response["Error"]["Code"] != "LoadBalancerNotFound":
                    raise
                tag_descriptions = []
                for item in chunk:
                    try:
                        tag_descriptions.extend(client.describe_tags(
                            ResourceArns=[item["LoadBalancerArn"]],
                        )["TagDescriptions"])
                    except ClientError as single_error:
                        if single_error.response["Error"]["Code"] != "LoadBalancerNotFound":
                            raise
            tag_by_arn = {
                item["ResourceArn"]: {tag["Key"]: tag["Value"] for tag in item["Tags"]}
                for item in tag_descriptions
            }
            for item in chunk:
                item_tags = tag_by_arn.get(item["LoadBalancerArn"], {})
                if (
                    item_tags.get("elbv2.k8s.aws/cluster") == CLUSTER
                    and item_tags.get("ingress.k8s.aws/stack") == STACK
                ):
                    yield item


def existing_record(client, zone_id, domain):
    result = client.list_resource_record_sets(
        HostedZoneId=zone_id,
        StartRecordName=domain,
        StartRecordType="A",
        MaxItems="1",
    )
    for record in result.get("ResourceRecordSets", []):
        if normalized(record["Name"]) == normalized(domain) and record["Type"] == "A":
            return record
    return None


def change_alias(route53, zone_id, action, record):
    result = route53.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch={"Comment": "Contact form ALB alias", "Changes": [
            {"Action": action, "ResourceRecordSet": record},
        ]},
    )
    route53.get_waiter("resource_record_sets_changed").wait(
        Id=result["ChangeInfo"]["Id"],
        WaiterConfig={"Delay": 10, "MaxAttempts": 30},
    )


def update_alias(args, elbv2, route53):
    matches = list(owned_balancers(elbv2))
    current = existing_record(route53, args.zone_id, args.domain)
    if args.action == "create":
        matches = [item for item in matches if normalized_alb_dns(item["DNSName"]) == normalized_alb_dns(args.dns_name)]
        if len(matches) != 1:
            raise RuntimeError("Ingress ALB is absent or does not have the expected ownership tags")
        alb = matches[0]
        alias = {
            "Name": f"{normalized(args.domain)}.",
            "Type": "A",
            "AliasTarget": {
                "DNSName": alb["DNSName"],
                "HostedZoneId": alb["CanonicalHostedZoneId"],
                "EvaluateTargetHealth": True,
            },
        }
        if current:
            existing_target = current.get("AliasTarget", {})
            if (
                normalized_alb_dns(existing_target.get("DNSName", "")) == normalized_alb_dns(alb["DNSName"])
                and existing_target.get("HostedZoneId") == alb["CanonicalHostedZoneId"]
                and existing_target.get("EvaluateTargetHealth") is True
            ):
                save_alias_record(args, alb)
                return False
            raise RuntimeError("An A record already exists for this domain; inspect it before changing DNS")
        change_alias(route53, args.zone_id, "CREATE", alias)
        save_alias_record(args, alb)
        return True

    if not current:
        clear_alias_record(args)
        return False
    target = current.get("AliasTarget", {})
    tagged_match = any(
        normalized_alb_dns(item["DNSName"]) == normalized_alb_dns(target.get("DNSName", ""))
        and item["CanonicalHostedZoneId"] == target.get("HostedZoneId")
        for item in matches
    )
    if not tagged_match and not record_matches_alias(args, current):
        raise RuntimeError("The existing A record does not point to this deployment's ALB")
    change_alias(route53, args.zone_id, "DELETE", current)
    clear_alias_record(args)
    return True


def wait_deleted(elbv2, timeout, vpc_id, dns_name=None):
    deadline = time.monotonic() + timeout
    while True:
        owned = list(owned_balancers(elbv2))
        all_balancers = elbv2.get_paginator("describe_load_balancers").paginate()
        in_workload_vpc_or_named = any(
            item.get("VpcId") == vpc_id
            or (dns_name and normalized_alb_dns(item["DNSName"]) == normalized_alb_dns(dns_name))
            for page in all_balancers for item in page["LoadBalancers"]
        )
        if not owned and not in_workload_vpc_or_named:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("The controller ALB still exists; do not destroy EKS or the VPC")
        time.sleep(min(15, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "remove", "wait-deleted"])
    parser.add_argument("--profile", default="contact-form-deployer")
    parser.add_argument("--zone-id")
    parser.add_argument("--domain")
    parser.add_argument("--dns-name")
    parser.add_argument("--vpc-id")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.action in ("create", "remove") and (not args.zone_id or not args.domain):
        parser.error("--zone-id and --domain are required for alias changes")
    if args.action == "create" and not args.dns_name:
        parser.error("--dns-name is required to create an alias")
    if args.action == "wait-deleted" and not args.vpc_id:
        parser.error("--vpc-id is required to verify ALB deletion")
    session = boto3.Session(profile_name=args.profile, region_name=REGION)
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != ACCOUNT or identity["Arn"].endswith(":root"):
        raise RuntimeError("AWS profile does not match the authorized non-root account")
    elbv2 = session.client("elbv2")
    if args.action == "wait-deleted":
        wait_deleted(elbv2, args.timeout, args.vpc_id, args.dns_name)
        print(json.dumps({"deleted": True}))
        return
    changed = update_alias(args, elbv2, session.client("route53"))
    print(json.dumps({"changed": changed, "action": args.action}))


if __name__ == "__main__":
    try:
        main()
    except (ClientError, RuntimeError, ValueError) as error:
        print(f"ALB management failed: {error}", file=sys.stderr)
        sys.exit(1)
