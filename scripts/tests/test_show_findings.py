"""Offline checks for the scoped Security Hub demo output."""

import contextlib
import copy
import io
import sys
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from scripts import show_findings


def finding(resource, control="RDS.8", status="FAILED"):
    return {
        "Id": "finding-1",
        "AwsAccountId": show_findings.ACCOUNT,
        "Region": show_findings.REGION,
        "ProductArn": show_findings.PRODUCT_ARN,
        "RecordState": "ACTIVE",
        "Compliance": {
            "SecurityControlId": control,
            "Status": status,
            "AssociatedStandards": [{"StandardsId": show_findings.FSBP_ID}],
        },
        "Resources": [resource],
        "UpdatedAt": "2026-09-28T10:00:00.000Z",
        "Description": "Do not print this description or any secret value",
    }


def fake_client(pages):
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = pages
    return client


class ShowFindingsTests(unittest.TestCase):
    def test_project_provisioners_group_finding_is_included(self):
        group = (f"arn:aws:iam::{show_findings.ACCOUNT}:"
                 "group/contact-form-provisioners")
        client = fake_client([{"Findings": [finding({"Id": group}, control="KMS.2")]}])

        self.assertEqual(show_findings.project_rows(client), [
            ("KMS.2", "FAILED", group, "2026-09-28T10:00:00.000Z"),
        ])
        self.assertFalse(show_findings.is_project_resource({
            "Id": group + "-other",
        }))

    def test_paginates_and_excludes_unrelated_or_non_fsbp_findings(self):
        project = finding({"Id": "vpc-123", "Tags": {"Project": show_findings.PROJECT}})
        project["Resources"].append({"Id": "arn:aws:s3:::unrelated-bucket"})
        other_standard = copy.deepcopy(project)
        other_standard["Compliance"]["AssociatedStandards"] = [
            {"StandardsId": "standards/cis-aws-foundations-benchmark/v/3.0.0"},
        ]
        other_account = copy.deepcopy(project)
        other_account["AwsAccountId"] = "000000000000"
        archived = copy.deepcopy(project)
        archived["RecordState"] = "ARCHIVED"
        other_region = copy.deepcopy(project)
        other_region["Region"] = "us-east-1"
        other_product = copy.deepcopy(project)
        other_product["ProductArn"] = "arn:aws:securityhub:ap-southeast-1::product/aws/guardduty"
        legacy = finding({
            "Id": ("arn:aws:rds:ap-southeast-1:203888389134:"
                   "db:contact-form-postgres"),
        })
        legacy["Compliance"].pop("AssociatedStandards")
        legacy["Compliance"].pop("SecurityControlId")
        legacy["ProductFields"] = {
            "StandardsArn": "arn:aws:securityhub:::" + show_findings.FSBP_ID,
            "ControlId": "RDS.8",
        }
        client = fake_client([
            {"Findings": [project, other_standard, other_account, archived]},
            {"Findings": [other_region, other_product, legacy]},
        ])

        rows = show_findings.project_rows(client)

        self.assertEqual(rows, [
            ("RDS.8", "FAILED", legacy["Resources"][0]["Id"],
             "2026-09-28T10:00:00.000Z"),
            ("RDS.8", "FAILED", "vpc-123", "2026-09-28T10:00:00.000Z"),
        ])
        client.get_paginator.assert_called_once_with("get_findings")
        filters = client.get_paginator.return_value.paginate.call_args.kwargs["Filters"]
        self.assertEqual(filters["RecordState"][0]["Value"], "ACTIVE")
        self.assertEqual(filters["AwsAccountId"][0]["Value"], show_findings.ACCOUNT)
        self.assertEqual(filters["ProductArn"][0]["Value"], show_findings.PRODUCT_ARN)

    def test_resource_names_are_anchored_to_project_and_account(self):
        owned = show_findings.is_project_resource
        self.assertTrue(owned({"Id": "i-123", "Tags": {"Project": show_findings.PROJECT}}))
        self.assertTrue(owned({"Id": "vpc-123", "Tags": {"Name": "contact-form-vpc"}}))
        self.assertTrue(owned({
            "Id": ("arn:aws:elasticloadbalancing:ap-southeast-1:203888389134:"
                   "loadbalancer/app/k8s-contactf-contactf-abc/123"),
        }))
        self.assertTrue(owned({
            "Id": ("arn:aws:secretsmanager:ap-southeast-1:203888389134:"
                   "secret:contact-form/app-123-abc"),
        }))
        self.assertFalse(owned({"Id": "arn:aws:s3:::unrelated-contact-form-evidence"}))
        self.assertFalse(owned({"Id": "vpc-123", "Tags": {"Name": "other-contact-form-vpc"}}))
        self.assertFalse(owned({
            "Id": "arn:aws:rds:us-east-1:203888389134:db:contact-form-postgres",
            "Tags": {"Project": show_findings.PROJECT},
        }))
        self.assertFalse(owned({
            "Id": "arn:aws:rds:ap-southeast-1:000000000000:db:contact-form-postgres",
            "Tags": {"Project": show_findings.PROJECT},
        }))

    def test_default_profile_output_is_concise_and_redacted(self):
        client = fake_client([{"Findings": [finding({
            "Id": "arn:aws:rds:ap-southeast-1:203888389134:db:contact-form-postgres",
        })]}])
        session = Mock()
        session.client.return_value = client
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["show_findings.py"]),
            patch.object(show_findings.boto3, "Session", return_value=session) as create,
            contextlib.redirect_stdout(output),
        ):
            show_findings.main()

        create.assert_called_once_with(profile_name="contact-form-deployer",
                                       region_name="ap-southeast-1")
        session.client.assert_called_once_with("securityhub")
        report = output.getvalue()
        self.assertIn("RDS.8 | FAILED | arn:aws:rds:", report)
        self.assertIn("Summary: 1 project resource finding(s); FAILED=1.", report)
        self.assertNotIn("Do not print this description", report)
        self.assertNotIn("secret value", report)

    def test_failed_later_page_does_not_print_partial_report(self):
        def pages():
            yield {"Findings": [finding({"Id": "i-123", "Tags": {
                "Project": show_findings.PROJECT,
            }})]}
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}},
                              "GetFindings")

        client = fake_client(pages())
        session = Mock()
        session.client.return_value = client
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["show_findings.py"]),
            patch.object(show_findings.boto3, "Session", return_value=session),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
        ):
            with self.assertRaises(SystemExit) as exit_result:
                show_findings.main()

        self.assertEqual(exit_result.exception.code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Security Hub read failed (AccessDenied)", errors.getvalue())

    def test_empty_result_does_not_claim_pass(self):
        client = fake_client([{"Findings": []}])
        session = Mock()
        session.client.return_value = client
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["show_findings.py"]),
            patch.object(show_findings.boto3, "Session", return_value=session),
            contextlib.redirect_stdout(output),
        ):
            show_findings.main()
        self.assertIn("No matching findings observed.", output.getvalue())
        self.assertIn("Zero matches do not prove", output.getvalue())


if __name__ == "__main__":
    unittest.main()
