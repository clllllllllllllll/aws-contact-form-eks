"""Local checks that teardown inventory stays scoped and fails closed."""

import contextlib
import io
import json
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from scripts import check_residual


def empty_session(denied_operations=()):
    """Return mocked, empty AWS inventories without making network calls."""
    session = Mock(region_name=check_residual.REGION)
    clients = {name: Mock() for name in (
        "sts", "ec2", "eks", "rds", "elbv2", "ecr", "secretsmanager", "kms",
    )}
    clients["sts"].get_caller_identity.return_value = {
        "Account": check_residual.ACCOUNT,
        "Arn": f"arn:aws:iam::{check_residual.ACCOUNT}:user/contact-form-deployer",
    }
    responses = {
        "describe_vpcs": {"Vpcs": []},
        "describe_nat_gateways": {"NatGateways": []},
        "describe_instances": {"Reservations": []},
        "describe_volumes": {"Volumes": []},
        "describe_snapshots": {"Snapshots": []},
        "list_clusters": {"clusters": []},
        "describe_db_instances": {"DBInstances": []},
        "describe_db_snapshots": {"DBSnapshots": []},
        "describe_db_instance_automated_backups": {"DBInstanceAutomatedBackups": []},
        "describe_load_balancers": {"LoadBalancers": []},
        "list_secrets": {"SecretList": []},
    }

    def paginator(operation):
        if operation in denied_operations:
            error = ClientError({
                "Error": {"Code": "AccessDenied", "Message": "denied"},
            }, "".join(part.title() for part in operation.split("_")))
            return Mock(paginate=Mock(side_effect=error))
        return Mock(paginate=Mock(return_value=[responses[operation]]))

    for client in clients.values():
        client.get_paginator.side_effect = paginator
    clients["ec2"].describe_addresses.return_value = {"Addresses": []}
    clients["ecr"].describe_repositories.return_value = {"repositories": []}
    clients["kms"].list_keys.return_value = {"Keys": [], "Truncated": False}
    session.client.side_effect = clients.__getitem__
    return session, clients


class CostGuardTests(unittest.TestCase):
    def test_residual_inventory_rejects_wrong_account_before_listing(self):
        session = Mock()
        session.region_name = check_residual.REGION
        session.client.return_value.get_caller_identity.return_value = {
            "Account": "000000000000",
            "Arn": "arn:aws:iam::000000000000:user/other",
        }
        with self.assertRaisesRegex(RuntimeError, "authorized non-root account"):
            check_residual.collect(session)
        self.assertEqual(session.client.call_args_list[0].args, ("sts",))
        self.assertEqual(len(session.client.call_args_list), 1)

    def test_vpc_denial_marks_dependents_unknown_and_checks_other_services(self):
        session, clients = empty_session({"describe_vpcs"})
        alb_arn = "arn:aws:elasticloadbalancing:ap-southeast-1:203888389134:loadbalancer/app/owned"
        clients["elbv2"].get_paginator.side_effect = lambda operation: Mock(
            paginate=Mock(return_value=[{"LoadBalancers": [{
                "LoadBalancerArn": alb_arn, "VpcId": "vpc-unread",
            }]}])
        )
        clients["elbv2"].describe_tags.return_value = {"TagDescriptions": [{"Tags": [
            {"Key": "elbv2.k8s.aws/cluster", "Value": "contact-form-eks"},
            {"Key": "ingress.k8s.aws/stack", "Value": "contact-form/contact-form"},
        ]}]}
        inventory = check_residual.collect(session)

        self.assertIsNone(inventory["resources"]["vpcs"])
        self.assertIsNone(inventory["resources"]["nat_gateways"])
        self.assertEqual(inventory["resources"]["elastic_ips"], [])
        self.assertEqual(inventory["resources"]["load_balancers"], [alb_arn])
        for section in ("nat_gateways", "elastic_ips", "load_balancers"):
            self.assertEqual(inventory["read_errors"][section]["code"],
                             "DependencyUnavailable")
        self.assertEqual(inventory["read_errors"]["vpcs"]["operation"],
                         "DescribeVpcs")
        clients["ec2"].describe_addresses.assert_called_once_with()
        clients["elbv2"].describe_tags.assert_called_once_with(ResourceArns=[alb_arn])
        self.assertEqual(inventory["resources"]["rds_instances"], [])
        self.assertEqual(inventory["resources"]["workload_kms_keys"], [])
        clients["rds"].get_paginator.assert_called()
        clients["kms"].list_keys.assert_called_once_with()

    def test_nat_denial_still_reports_tagged_detached_eip_inconclusively(self):
        session, clients = empty_session({"describe_nat_gateways"})
        clients["ec2"].describe_addresses.return_value = {"Addresses": [
            {"AllocationId": "eip-detached", "Tags": [
                {"Key": "Project", "Value": check_residual.PROJECT},
                {"Key": "Lifecycle", "Value": check_residual.LIFECYCLE},
            ]},
            {"AllocationId": "eip-unrelated", "Tags": [
                {"Key": "Project", "Value": "other"},
            ]},
        ]}
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["check_residual.py"]),
            patch.object(check_residual.boto3, "Session", return_value=session),
            contextlib.redirect_stdout(output),
        ):
            exit_code = check_residual.main()

        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["inventory_status"], "inconclusive")
        self.assertTrue(report["runtime_resources_remaining"])
        self.assertIsNone(report["resources"]["nat_gateways"])
        self.assertEqual(report["resources"]["elastic_ips"], ["eip-detached"])
        self.assertEqual(report["read_errors"]["nat_gateways"]["operation"],
                         "DescribeNatGateways")
        self.assertEqual(report["read_errors"]["elastic_ips"]["code"],
                         "DependencyUnavailable")
        clients["ec2"].describe_addresses.assert_called_once_with()

    def test_nat_and_address_denials_report_both_read_failures(self):
        session, clients = empty_session({"describe_nat_gateways"})
        clients["ec2"].describe_addresses.side_effect = ClientError({
            "Error": {"Code": "AccessDenied", "Message": "addresses denied"},
        }, "DescribeAddresses")

        inventory = check_residual.collect(session)

        self.assertIsNone(inventory["resources"]["elastic_ips"])
        self.assertEqual(inventory["read_errors"]["elastic_ips"]["code"],
                         "DependencyUnavailable")
        self.assertEqual(inventory["read_errors"]["elastic_ips"]["read_error"], {
            "code": "AccessDenied", "operation": "DescribeAddresses",
            "message": "addresses denied",
        })

    def test_snapshot_denial_keeps_successful_sections_and_returns_inconclusive(self):
        session, clients = empty_session({"describe_snapshots"})
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["check_residual.py"]),
            patch.object(check_residual.boto3, "Session", return_value=session),
            contextlib.redirect_stdout(output),
        ):
            exit_code = check_residual.main()

        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["inventory_status"], "inconclusive")
        self.assertIsNone(report["runtime_resources_remaining"])
        self.assertEqual(report["resources"]["ebs_volumes"], [])
        self.assertIsNone(report["resources"]["ebs_snapshots"])
        self.assertEqual(report["resources"]["rds_automated_backups"], [])
        self.assertEqual(report["resources"]["application_secrets"], [])
        self.assertEqual(report["read_errors"], {"ebs_snapshots": {
            "code": "AccessDenied", "operation": "DescribeSnapshots", "message": "denied",
        }})
        self.assertIn("may still incur charges", report["scope_note"])
        clients["rds"].get_paginator.assert_called()
        clients["secretsmanager"].get_paginator.assert_called_once_with("list_secrets")

    def test_known_leftover_with_failed_read_is_still_inconclusive(self):
        session, clients = empty_session({"describe_snapshots", "describe_db_snapshots"})
        clients["ec2"].describe_addresses.return_value = {"Addresses": [{
            "AllocationId": "eip-owned",
            "Tags": [
                {"Key": "Project", "Value": check_residual.PROJECT},
                {"Key": "Lifecycle", "Value": check_residual.LIFECYCLE},
            ],
        }]}
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["check_residual.py"]),
            patch.object(check_residual.boto3, "Session", return_value=session),
            contextlib.redirect_stdout(output),
        ):
            exit_code = check_residual.main()

        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["inventory_status"], "inconclusive")
        self.assertTrue(report["runtime_resources_remaining"])
        self.assertEqual(report["resources"]["elastic_ips"], ["eip-owned"])
        self.assertEqual(set(report["read_errors"]), {"ebs_snapshots", "rds_snapshots"})
        self.assertEqual(report["resources"]["application_secrets"], [])
        clients["secretsmanager"].get_paginator.assert_called_once_with("list_secrets")

    def test_vpc_inventory_keeps_workload_vpc_when_name_tag_is_missing(self):
        ec2 = Mock()
        ec2.get_paginator.return_value.paginate.return_value = [{"Vpcs": [
            {"VpcId": "vpc-owned", "Tags": [
                {"Key": "Project", "Value": check_residual.PROJECT},
                {"Key": "Lifecycle", "Value": "workload"},
            ]},
            {"VpcId": "vpc-unrelated", "Tags": [{"Key": "Name", "Value": "other"}]},
        ]}]
        self.assertEqual(check_residual.vpc_inventory(ec2), {"vpc-owned"})

    def test_nat_inventory_finds_untagged_gateway_and_its_eip_in_workload_vpc(self):
        ec2 = Mock()
        ec2.get_paginator.return_value.paginate.return_value = [{"NatGateways": [
            {"NatGatewayId": "nat-owned", "VpcId": "vpc-owned", "State": "available",
             "NatGatewayAddresses": [{"AllocationId": "eip-owned"}]},
            {"NatGatewayId": "nat-named", "VpcId": "vpc-other", "State": "available",
             "Tags": [{"Key": "Name", "Value": "contact-form-nat-b"}]},
            {"NatGatewayId": "nat-unrelated", "VpcId": "vpc-other", "State": "available"},
            {"NatGatewayId": "nat-deleted", "VpcId": "vpc-owned", "State": "deleted"},
        ]}]
        ec2.describe_addresses.return_value = {"Addresses": [
            {"AllocationId": "eip-owned"},
            {"AllocationId": "eip-named", "Tags": [
                {"Key": "Name", "Value": "contact-form-nat-a"},
            ]},
            {"AllocationId": "eip-unrelated"},
        ]}
        self.assertEqual(check_residual.nat_inventory(ec2, {"vpc-owned"}), (
            ["nat-named", "nat-owned"], ["eip-named", "eip-owned"],
        ))
        self.assertEqual(ec2.get_paginator.return_value.paginate.call_args.kwargs, {})
        self.assertEqual(ec2.describe_addresses.call_args.kwargs, {})

    def test_nat_inventory_finds_detached_workload_eip_without_name_tag(self):
        ec2 = Mock()
        ec2.get_paginator.return_value.paginate.return_value = [{"NatGateways": []}]
        ec2.describe_addresses.return_value = {"Addresses": [
            {"AllocationId": "eip-detached", "Tags": [
                {"Key": "Project", "Value": check_residual.PROJECT},
                {"Key": "Lifecycle", "Value": check_residual.LIFECYCLE},
            ]},
            {"AllocationId": "eip-unrelated", "Tags": [
                {"Key": "Project", "Value": check_residual.PROJECT},
                {"Key": "Lifecycle", "Value": "foundation"},
            ]},
        ]}
        self.assertEqual(check_residual.nat_inventory(ec2, set()), (
            [], ["eip-detached"],
        ))

    def test_ebs_inventory_includes_only_tagged_workload_resources(self):
        owned = [
            {"Key": "Project", "Value": check_residual.PROJECT},
            {"Key": "Lifecycle", "Value": "workload"},
            {"Key": "Name", "Value": "contact-form-eks-worker-root"},
        ]
        foundation = [
            {"Key": "Project", "Value": check_residual.PROJECT},
            {"Key": "Lifecycle", "Value": "foundation"},
        ]
        ec2 = Mock()
        paginators = {
            "describe_volumes": Mock(paginate=Mock(return_value=[{"Volumes": [
                {"VolumeId": "vol-owned", "State": "available", "Tags": owned},
                {"VolumeId": "vol-foundation", "State": "available", "Tags": foundation},
            ]}])),
            "describe_snapshots": Mock(paginate=Mock(return_value=[{"Snapshots": [
                {"SnapshotId": "snap-owned", "Tags": owned},
                {"SnapshotId": "snap-foundation", "Tags": foundation},
            ]}])),
        }
        ec2.get_paginator.side_effect = lambda operation: paginators[operation]
        self.assertEqual(check_residual.ebs_inventory(ec2), (["vol-owned"], ["snap-owned"]))
        self.assertEqual(paginators["describe_snapshots"].paginate.call_args.kwargs["OwnerIds"], ["self"])

    def test_retained_rds_backup_is_reported_after_instance_deletion(self):
        rds = Mock()
        rds.get_paginator.return_value.paginate.return_value = [{"DBInstanceAutomatedBackups": [
            {"DBInstanceIdentifier": check_residual.DATABASE_ID,
             "DbiResourceId": "db-old", "Status": "retained"},
            {"DBInstanceIdentifier": "unrelated-db", "DbiResourceId": "db-other", "Status": "retained"},
        ]}]
        self.assertEqual(check_residual.rds_automated_backups(rds), [
            {"resource_id": "db-old", "status": "retained"},
        ])
        self.assertEqual(rds.get_paginator.return_value.paginate.call_args.kwargs["Filters"], [
            {"Name": "db-instance-id", "Values": [check_residual.DATABASE_ID]},
        ])

    def test_kms_inventory_records_owned_key_pending_deletion(self):
        kms = Mock()
        kms.list_keys.side_effect = [
            {"Keys": [{"KeyId": "key-owned"}], "Truncated": True, "NextMarker": "next"},
            {"Keys": [{"KeyId": "key-foundation"}], "Truncated": False},
        ]
        deletion_date = datetime(2026, 10, 4, tzinfo=timezone.utc)
        metadata = {
            "key-owned": {"AWSAccountId": check_residual.ACCOUNT, "KeyManager": "CUSTOMER",
                          "Arn": "arn:aws:kms:ap-southeast-1:203888389134:key/key-owned",
                          "KeyState": "PendingDeletion", "DeletionDate": deletion_date},
            "key-foundation": {"AWSAccountId": check_residual.ACCOUNT, "KeyManager": "CUSTOMER",
                               "Arn": "arn:aws:kms:ap-southeast-1:203888389134:key/key-foundation",
                               "KeyState": "Enabled"},
        }
        kms.describe_key.side_effect = lambda KeyId: {"KeyMetadata": metadata[KeyId]}
        tag_sets = {
            "key-owned": [
                {"TagKey": "Project", "TagValue": check_residual.PROJECT},
                {"TagKey": "Lifecycle", "TagValue": "workload"},
            ],
            "key-foundation": [
                {"TagKey": "Project", "TagValue": check_residual.PROJECT},
                {"TagKey": "Lifecycle", "TagValue": "foundation"},
            ],
        }
        kms.list_resource_tags.side_effect = lambda KeyId: {
            "Tags": tag_sets[KeyId], "Truncated": False,
        }
        self.assertEqual(check_residual.kms_inventory(kms), [{
            "arn": metadata["key-owned"]["Arn"],
            "state": "PendingDeletion",
            "deletion_date": deletion_date.isoformat(),
        }])
        self.assertEqual(kms.list_keys.call_args_list[1].kwargs, {"Marker": "next"})

    def test_kms_pending_deletion_is_informational_but_other_states_block(self):
        for state, expected_code in (
            ("PendingDeletion", 0),
            ("Enabled", 2),
            ("Disabled", 2),
            ("PendingReplicaDeletion", 2),
        ):
            with self.subTest(state=state):
                key = {"arn": "arn:aws:kms:ap-southeast-1:203888389134:key/owned",
                       "state": state}
                output = io.StringIO()
                with (
                    patch.object(sys, "argv", ["check_residual.py"]),
                    patch.object(check_residual.boto3, "Session"),
                    patch.object(check_residual, "collect",
                                 return_value={"resources": {"workload_kms_keys": [key]},
                                               "read_errors": {}}),
                    contextlib.redirect_stdout(output),
                ):
                    exit_code = check_residual.main()
                report = json.loads(output.getvalue())
                self.assertEqual(exit_code, expected_code)
                self.assertEqual(report["runtime_resources_remaining"], expected_code == 2)
                self.assertEqual(report["read_errors"], {})
                self.assertEqual(
                    report["expected_pending_cleanup"]["workload_kms_keys"],
                    [key] if state == "PendingDeletion" else [],
                )
                self.assertEqual(
                    report["resources"]["workload_kms_keys"],
                    [] if state == "PendingDeletion" else [key],
                )

    def test_pending_key_does_not_hide_another_runtime_leftover(self):
        pending = {"arn": "arn:aws:kms:ap-southeast-1:203888389134:key/owned",
                   "state": "PendingDeletion"}
        resources, expected = check_residual.classify_resources({
            "ebs_volumes": ["vol-owned"], "workload_kms_keys": [pending],
        })
        self.assertEqual(resources["ebs_volumes"], ["vol-owned"])
        self.assertEqual(resources["workload_kms_keys"], [])
        self.assertEqual(expected["workload_kms_keys"], [pending])
        self.assertTrue(any(resources.values()))

    def test_denied_ebs_read_is_not_a_clean_inventory(self):
        ec2 = Mock()
        ec2.get_paginator.return_value.paginate.side_effect = ClientError({
            "Error": {"Code": "AccessDenied", "Message": "denied"},
        }, "DescribeVolumes")
        with self.assertRaises(ClientError):
            check_residual.ebs_inventory(ec2)



if __name__ == "__main__":
    unittest.main()
