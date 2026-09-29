#!/usr/bin/env python3
"""Concise, read-only review of the three staged workload Terraform plans."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ZONES = ("ap-southeast-1a", "ap-southeast-1b")
PROJECT_TAGS = {
    "Project": "aws-contact-form-eks",
    "ManagedBy": "Terraform",
    "Lifecycle": "workload",
}


def zoned(address: str) -> set[str]:
    return {f'{address}["{zone}"]' for zone in ZONES}


EXPECTED_FIRST = {"aws_kms_key.eks", "aws_secretsmanager_secret.app"}
EXPECTED_CLUSTER = (
    {
        "aws_eks_cluster.main",
        "aws_iam_role.cluster",
        "aws_iam_role_policy_attachment.cluster",
        "aws_internet_gateway.main",
        "aws_route_table.public",
        "aws_vpc.main",
    }
    | zoned("aws_eip.nat")
    | zoned("aws_nat_gateway.main")
    | zoned("aws_route_table.app")
    | zoned("aws_route_table_association.app")
    | zoned("aws_route_table_association.public")
    | zoned("aws_subnet.app")
    | zoned("aws_subnet.public")
)
EXPECTED_FULL = (
    {
        "aws_db_instance.main",
        "aws_db_subnet_group.main",
        "aws_ecr_repository.app",
        "aws_eks_access_entry.deployer",
        "aws_eks_access_policy_association.deployer",
        "aws_eks_addon.coredns",
        "aws_eks_addon.kube_proxy",
        "aws_eks_addon.vpc_cni",
        "aws_iam_instance_profile.relay",
        "aws_iam_openid_connect_provider.cluster",
        "aws_iam_role.nodes",
        "aws_iam_role.relay",
        "aws_iam_role_policy.app_secret",
        "aws_iam_role_policy.controller",
        "aws_iam_role_policy.database_setup",
        "aws_iam_role_policy_attachment.cni",
        "aws_iam_role_policy_attachment.nodes_ecr",
        "aws_iam_role_policy_attachment.nodes_worker",
        "aws_iam_role_policy_attachment.relay",
        "aws_instance.relay",
        "aws_launch_template.nodes",
        "aws_security_group.alb",
        "aws_security_group.nodes",
        "aws_security_group.rds",
        "aws_security_group.relay",
        "aws_vpc_security_group_egress_rule.alb_to_nodes",
        "aws_vpc_security_group_egress_rule.nodes_outbound",
        "aws_vpc_security_group_egress_rule.relay_dns_tcp",
        "aws_vpc_security_group_egress_rule.relay_dns_udp",
        "aws_vpc_security_group_egress_rule.relay_https",
        "aws_vpc_security_group_ingress_rule.alb_http",
        "aws_vpc_security_group_ingress_rule.alb_https",
        "aws_vpc_security_group_ingress_rule.api_from_nodes",
        "aws_vpc_security_group_ingress_rule.api_from_relay",
        "aws_vpc_security_group_ingress_rule.node_from_alb",
        "aws_vpc_security_group_ingress_rule.node_self",
        "aws_vpc_security_group_ingress_rule.nodes_from_control_plane",
        "aws_vpc_security_group_ingress_rule.rds_from_nodes",
    }
    | zoned("aws_eks_node_group.per_az")
)

# IRSA roles have service-name keys; AZ-keyed resources are added separately.
EXPECTED_FULL = (
    EXPECTED_FULL
    | {f'aws_iam_role.irsa["{name}"]' for name in ("app", "cni", "controller", "setup")}
    | zoned("aws_eks_node_group.per_az")
    | zoned("aws_route_table.database")
    | zoned("aws_route_table_association.database")
    | zoned("aws_subnet.database")
)
EXPECTED = {
    "first": EXPECTED_FIRST,
    "cluster": EXPECTED_CLUSTER,
    "full": EXPECTED_FULL,
}
KNOWN_DRIFT = {
    "first": {},
    "cluster": {"aws_kms_key.eks": {"tags"}},
    "full": {
        **{address: {"association_id", "network_interface", "private_dns", "private_ip"} for address in zoned("aws_eip.nat")},
        "aws_eks_cluster.main": {"tags", "vpc_config"},
        "aws_iam_role.cluster": {"managed_policy_arns", "tags"},
        "aws_secretsmanager_secret.app": {"tags"},
    },
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(2)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def after(changes: dict[str, dict], address: str) -> dict:
    require(address in changes, f"missing resource {address}")
    return changes[address]["change"].get("after") or {}


def tagged(value: dict) -> bool:
    tags = value.get("tags_all") or {}
    return all(tags.get(key) == expected for key, expected in PROJECT_TAGS.items())


def check_first(changes: dict[str, dict]) -> None:
    key = after(changes, "aws_kms_key.eks")
    secret = after(changes, "aws_secretsmanager_secret.app")
    require(key.get("enable_key_rotation") is True, "EKS KMS rotation must be enabled")
    require(key.get("key_usage") == "ENCRYPT_DECRYPT", "unexpected EKS key usage")
    require(secret.get("name_prefix") == "contact-form/app-", "unexpected app secret prefix")
    require(secret.get("recovery_window_in_days") == 0, "unexpected app secret deletion window")
    require(tagged(key) and tagged(secret), "first-target ownership tags differ")
    print("PASS: EKS KMS key and empty app-secret entry have expected settings and tags")


def check_cluster(changes: dict[str, dict]) -> None:
    cluster = after(changes, "aws_eks_cluster.main")
    vpc = (cluster.get("vpc_config") or [{}])[0]
    encryption = (cluster.get("encryption_config") or [{}])[0]
    access = (cluster.get("access_config") or [{}])[0]
    require(cluster.get("name") == "contact-form-eks" and cluster.get("version") == "1.36", "unexpected EKS name/version")
    require(vpc.get("endpoint_private_access") is True and vpc.get("endpoint_public_access") is False, "EKS API must be private only")
    require(set(encryption.get("resources") or []) == {"secrets"}, "EKS secrets encryption is missing")
    require(set(cluster.get("enabled_cluster_log_types") or []) == {"api", "audit", "authenticator", "controllerManager", "scheduler"}, "EKS control-plane logs differ")
    require(access.get("bootstrap_cluster_creator_admin_permissions") is False, "unexpected cluster-creator admin bootstrap")
    require(tagged(cluster), "EKS ownership tags differ")
    for zone in ZONES:
        subnet = after(changes, f'aws_subnet.app["{zone}"]')
        require(subnet.get("availability_zone") == zone and subnet.get("map_public_ip_on_launch") is False, f"app subnet {zone} is not private")
    print("PASS: EKS 1.36 has private API, encrypted secrets, five logs and two private AZ subnets")


def check_full(changes: dict[str, dict]) -> None:
    db = after(changes, "aws_db_instance.main")
    expected_db = {
        "engine": "postgres",
        "engine_version": "16",
        "instance_class": "db.t4g.small",
        "multi_az": True,
        "publicly_accessible": False,
        "storage_encrypted": True,
        "manage_master_user_password": True,
        "allocated_storage": 20,
        "max_allocated_storage": 40,
        "deletion_protection": False,
    }
    require(all(db.get(key) == value for key, value in expected_db.items()), "RDS configuration differs from the reviewed private Multi-AZ design")
    require(set(db.get("enabled_cloudwatch_logs_exports") or []) == {"postgresql", "upgrade"}, "RDS log exports differ")
    require(tagged(db), "RDS ownership tags differ")
    print("PASS: private encrypted Multi-AZ PostgreSQL 16; RDS-managed master secret; 20–40 GiB")

    app_subnets = {}
    for zone in ZONES:
        app = after(changes, f'aws_subnet.app["{zone}"]')
        database = after(changes, f'aws_subnet.database["{zone}"]')
        app_subnets[zone] = app.get("id")
        require(app.get("availability_zone") == zone and app.get("map_public_ip_on_launch") is False, f"app subnet {zone} is not private")
        require(database.get("availability_zone") == zone and database.get("map_public_ip_on_launch") is False, f"database subnet {zone} is not private")
        worker = after(changes, f'aws_eks_node_group.per_az["{zone}"]')
        scaling = (worker.get("scaling_config") or [{}])[0]
        require(worker.get("instance_types") == ["t3.medium"], f"worker instance type differs in {zone}")
        require(scaling == {"desired_size": 1, "max_size": 1, "min_size": 1}, f"worker count differs in {zone}")
        require(worker.get("subnet_ids") == [app_subnets[zone]], f"worker subnet differs in {zone}")
    print("PASS: one t3.medium worker per AZ; private application and database subnets")

    relay = after(changes, "aws_instance.relay")
    metadata = (relay.get("metadata_options") or [{}])[0]
    require(relay.get("instance_type") == "t3.micro", "unexpected relay instance type")
    require(relay.get("subnet_id") in set(app_subnets.values()), "relay is not in an app subnet")
    require(relay.get("associate_public_ip_address") is False, "relay has a public IP")
    require(metadata.get("http_tokens") == "required", "relay IMDSv2 is not required")
    print("PASS: private t3.micro SSM relay with IMDSv2 required")

    oidc = after(changes, "aws_iam_openid_connect_provider.cluster").get("url")
    cluster = after(changes, "aws_eks_cluster.main")
    identity = (cluster.get("identity") or [{}])[0]
    issuer = (identity.get("oidc") or [{}])[0].get("issuer")
    require(oidc and oidc == issuer, "OIDC provider URL does not match EKS issuer")
    vpc = (cluster.get("vpc_config") or [{}])[0]
    require(vpc.get("endpoint_private_access") is True and vpc.get("endpoint_public_access") is False, "EKS API is no longer private only")
    require(tagged(cluster) and tagged(after(changes, "aws_secretsmanager_secret.app")), "existing EKS or app-secret ownership tags differ")
    require(all(changes[address]["change"]["actions"] == ["no-op"] for address in EXPECTED_FIRST | {"aws_eks_cluster.main"}), "first-target resource or EKS cluster would change")
    print("PASS: IRSA OIDC URL matches EKS; key, secret and cluster stay unchanged")


def check_drift(stage: str, drift: list[dict]) -> None:
    for item in drift:
        address = item["address"]
        allowed_fields = KNOWN_DRIFT[stage].get(address)
        require(allowed_fields is not None, f"unexpected AWS drift on {address}")
        before = item["change"].get("before") or {}
        current = item["change"].get("after") or {}
        changed_fields = {key for key in set(before) | set(current) if before.get(key) != current.get(key)}
        require(changed_fields <= allowed_fields, f"unexpected drift fields on {address}: {sorted(changed_fields - allowed_fields)}")
        if "tags" in changed_fields:
            require(current.get("tags") == {}, f"unexpected explicit tags on {address}")
            require(tagged(current), f"ownership tags changed on {address}")
        if address.startswith("aws_eip.nat"):
            require(current.get("association_id"), f"NAT EIP is not associated: {address}")
        if address == "aws_eks_cluster.main":
            vpc = (current.get("vpc_config") or [{}])[0]
            require(vpc.get("endpoint_private_access") is True and vpc.get("endpoint_public_access") is False, "EKS API drifted to public access")
    if drift:
        print(f"PASS: {len(drift)} known AWS metadata refreshes; no unexpected drift")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=EXPECTED)
    parser.add_argument("plan", type=Path, help="saved workload .tfplan file")
    args = parser.parse_args()
    require(args.plan.is_file(), "saved plan file does not exist")
    command = ["terraform", "-chdir=terraform/workload", "show", "-json", str(args.plan.resolve())]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    require(result.returncode == 0, "terraform could not read the saved plan")
    try:
        plan = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail("terraform did not return valid plan JSON")
    require(plan.get("applyable") is True and plan.get("errored") is False, "plan is not applyable")
    changes = {item["address"]: item for item in plan["resource_changes"]}
    creates = {address for address, item in changes.items() if item["change"]["actions"] == ["create"]}
    invalid = {address: item["change"]["actions"] for address, item in changes.items() if item["change"]["actions"] not in (["create"], ["no-op"], ["read"])}
    require(not invalid, f"unexpected change/destroy/replacement actions: {invalid}")
    expected = EXPECTED[args.stage]
    require(creates == expected, f"resource set differs; missing={sorted(expected - creates)}, unexpected={sorted(creates - expected)}")
    print(f"PASS: {args.stage} plan; {len(creates)} exact expected creates, no changes/destroys/replacements")
    {"first": check_first, "cluster": check_cluster, "full": check_full}[args.stage](changes)
    check_drift(args.stage, plan.get("resource_drift") or [])
    print("PLAN CHECK PASS — review the cost and saved plan before apply")


if __name__ == "__main__":
    main()
