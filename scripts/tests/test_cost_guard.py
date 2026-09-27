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

    def test_residual_inventory_propagates_denied_reads(self):
        session = Mock()
        session.region_name = check_residual.REGION
        ec2 = Mock()
        ec2.get_paginator.return_value.paginate.side_effect = ClientError({
            "Error": {"Code": "AccessDenied", "Message": "denied"},
        }, "DescribeVpcs")
        session.client.side_effect = lambda service: {
            "sts": Mock(get_caller_identity=Mock(return_value={
                "Account": check_residual.ACCOUNT,
                "Arn": f"arn:aws:iam::{check_residual.ACCOUNT}:user/contact-form-deployer",
            })),
            "ec2": ec2,
        }[service]
        with self.assertRaises(ClientError):
            check_residual.collect(session)

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
                                 return_value={"workload_kms_keys": [key]}),
                    contextlib.redirect_stdout(output),
                ):
                    exit_code = check_residual.main()
                report = json.loads(output.getvalue())
                self.assertEqual(exit_code, expected_code)
                self.assertEqual(report["runtime_resources_remaining"], expected_code == 2)
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
