"""Local checks that teardown inventory fails closed and readback excludes real addresses."""

import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from scripts import check_residual


class CostGuardTests(unittest.TestCase):
    def test_residual_inventory_rejects_wrong_account_before_listing(self):
        session = Mock()
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
        session.client.side_effect = lambda service: {
            "sts": Mock(get_caller_identity=Mock(return_value={
                "Account": check_residual.ACCOUNT,
                "Arn": f"arn:aws:iam::{check_residual.ACCOUNT}:user/contact-form-deployer",
            })),
            "ec2": Mock(describe_vpcs=Mock(side_effect=ClientError({
                "Error": {"Code": "AccessDenied", "Message": "denied"},
            }, "DescribeVpcs"))),
        }[service]
        with self.assertRaises(ClientError):
            check_residual.collect(session)



if __name__ == "__main__":
    unittest.main()
