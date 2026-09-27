"""Local preflight and controller policy checks without AWS calls."""

import contextlib
import io
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from botocore.exceptions import ClientError

from scripts import preflight


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = {
    "kubernetes_version": "1.33",
    "addon_versions": {"vpc_cni": "vpc-cni-test", "kube_proxy": "kube-proxy-test", "coredns": "coredns-test"},
    "node_release_version": "1.33.10-20260409",
    "relay_ami_id": "ami-00000000000000002",
}


NODE_AMI = "ami-00000000000000001"
NODE_IMAGE_NAME = "amazon-eks-node-al2023-x86_64-standard-1.33-v20260409"
FROZEN_VERSIONS = dict(VERSIONS, node_ami_id=NODE_AMI, node_ssm_parameter_version=7)


def ami_clients(current_release=VERSIONS["node_release_version"], current_version=7):
    minor = VERSIONS["kubernetes_version"]
    recommended_path = (
        f"/aws/service/eks/optimized-ami/{minor}/amazon-linux-2023/x86_64/standard/recommended"
    )
    current_date = current_release.split("-")[1]
    current_name = f"amazon-eks-node-al2023-x86_64-standard-{minor}-v{current_date}"
    selected = {
        "release_version": VERSIONS["node_release_version"],
        "image_id": NODE_AMI,
        "image_name": NODE_IMAGE_NAME,
    }
    current = {
        "release_version": current_release,
        "image_id": NODE_AMI if current_version == 7 else "ami-00000000000000003",
        "image_name": current_name,
    }
    parameters = {
        recommended_path: {"Value": json.dumps(current), "Version": current_version},
        f"{recommended_path}:7": {"Value": json.dumps(selected), "Version": 7},
    }
    ssm = Mock()
    ssm.get_parameter.side_effect = lambda Name: {"Parameter": parameters[Name]}
    names = {
        NODE_AMI: NODE_IMAGE_NAME,
        VERSIONS["relay_ami_id"]: "al2023-ami-kernel-default-x86_64-test",
    }
    ec2 = Mock()
    ec2.describe_images.side_effect = lambda ImageIds, Owners: {"Images": [{
        "ImageId": ImageIds[0], "Name": names[ImageIds[0]],
        "State": "available", "Architecture": "x86_64", "RootDeviceType": "ebs",
    }]}
    return ec2, ssm, recommended_path


def capacity_clients(quota):
    ec2 = Mock()
    ec2.get_paginator.side_effect = lambda operation: {
        "describe_instances": Mock(paginate=Mock(return_value=[{"Reservations": []}])),
        "describe_instance_types": Mock(paginate=Mock(return_value=[{
            "InstanceTypes": [
                {"InstanceType": name, "VCpuInfo": {"DefaultVCpus": 2}}
                for name in ("t3.medium", "t3.micro")
            ]
        }])),
    }[operation]
    quotas = Mock()
    quotas.get_service_quota.return_value = {"Quota": {"Value": quota}}
    return ec2, quotas


class PreflightTests(unittest.TestCase):
    def test_eks_version_request_uses_one_filter_and_requires_standard_support(self):
        eks = Mock()
        version_paginator = Mock()
        addon_paginator = Mock()
        support_status = "STANDARD_SUPPORT"

        def paginate_versions(**arguments):
            filters = {"defaultOnly", "clusterVersions", "includeAll", "status", "versionStatus"}
            if len(filters.intersection(arguments)) != 1:
                raise ValueError("EKS accepts only one cluster version filter")
            self.assertEqual(arguments, {"clusterVersions": [VERSIONS["kubernetes_version"]]})
            return [{"clusterVersions": [{
                "clusterVersion": VERSIONS["kubernetes_version"],
                "versionStatus": support_status,
            }]}]

        def paginate_addons(**arguments):
            pin = next(
                VERSIONS["addon_versions"][key]
                for key, name in preflight.ADDONS.items()
                if name == arguments["addonName"]
            )
            return [{"addons": [{
                "addonName": arguments["addonName"],
                "addonVersions": [{
                    "addonVersion": pin,
                    "compatibilities": [{"clusterVersion": VERSIONS["kubernetes_version"]}],
                }],
            }]}]

        version_paginator.paginate.side_effect = paginate_versions
        addon_paginator.paginate.side_effect = paginate_addons
        eks.get_paginator.side_effect = lambda operation: {
            "describe_cluster_versions": version_paginator,
            "describe_addon_versions": addon_paginator,
        }[operation]

        self.assertEqual(
            preflight.check_eks(eks, VERSIONS)["kubernetes_version"],
            VERSIONS["kubernetes_version"],
        )
        support_status = "EXTENDED_SUPPORT"
        with self.assertRaisesRegex(preflight.Blocked, "not confirmed in standard support"):
            preflight.check_eks(eks, VERSIONS)

    def test_six_free_vcpus_pass_initial_gate_but_not_required_update_headroom(self):
        ec2, quotas = capacity_clients(6)
        capacity = preflight.standard_capacity(ec2, quotas)
        self.assertEqual(capacity["new_base_vcpus"], 6)
        self.assertEqual(capacity["new_simultaneous_update_peak_vcpus"], 14)
        self.assertFalse(capacity["simultaneous_update_headroom_ready"])
        with self.assertRaisesRegex(preflight.Blocked, "simultaneous node updates"):
            preflight.standard_capacity(ec2, quotas, require_update_headroom=True)

    def test_five_free_vcpus_blocks_initial_stack(self):
        ec2, quotas = capacity_clients(5)
        with self.assertRaisesRegex(preflight.Blocked, "new base needs 6"):
            preflight.standard_capacity(ec2, quotas)

    def test_initial_recommended_release_records_exact_version_and_ami(self):
        ec2, ssm, recommended_path = ami_clients()
        result = preflight.check_amis(ec2, ssm, VERSIONS)
        self.assertEqual(result["node_ssm_parameter_version"], 7)
        self.assertEqual(result["node_ami"]["image_id"], NODE_AMI)
        self.assertFalse(result["recommendation_drift"])
        ssm.get_parameter.assert_called_once_with(Name=recommended_path)

    def test_pinned_node_release_remains_valid_after_recommendation_advances(self):
        ec2, ssm, recommended_path = ami_clients(
            current_release="1.33.13-20260801", current_version=8
        )
        result = preflight.check_amis(ec2, ssm, FROZEN_VERSIONS)
        self.assertEqual(result["node_release_version"], VERSIONS["node_release_version"])
        self.assertEqual(result["node_ami"]["image_id"], NODE_AMI)
        self.assertEqual(result["node_ssm_parameter_version"], 7)
        self.assertTrue(result["recommendation_drift"])
        self.assertEqual(result["recommended_node_release_version"], "1.33.13-20260801")
        self.assertEqual(ssm.get_parameter.call_args_list, [
            call(Name=recommended_path), call(Name=f"{recommended_path}:7")
        ])

    def test_fabricated_release_patch_is_rejected(self):
        ec2, ssm, _ = ami_clients(current_release="1.33.13-20260801", current_version=8)
        fabricated = dict(FROZEN_VERSIONS, node_release_version="1.33.99-20260409")
        with self.assertRaisesRegex(preflight.Blocked, "pinned node release"):
            preflight.check_amis(ec2, ssm, fabricated)
        ec2.describe_images.assert_not_called()

    def test_denied_read_is_incomplete_and_preserves_verified_file(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.json"
            verified = Path(directory) / "verified.json"
            candidate.write_text(json.dumps(VERSIONS))
            preflight.save_verified_versions(verified, FROZEN_VERSIONS)
            original = verified.read_bytes()
            denied = ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetCallerIdentity")
            output = io.StringIO()
            with (
                patch.object(sys, "argv", ["preflight.py", "--versions-file", str(candidate),
                                           "--verified-file", str(verified)]),
                patch.object(preflight.boto3, "Session", side_effect=denied) as session,
                contextlib.redirect_stdout(output),
            ):
                exit_code = preflight.main()
            self.assertEqual(exit_code, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "INCOMPLETE")
            session.assert_called_once()
            self.assertEqual(verified.read_bytes(), original)

    def test_differing_existing_pins_block_before_aws_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.json"
            verified = Path(directory) / "verified.json"
            candidate.write_text(json.dumps(dict(
                VERSIONS, relay_ami_id="ami-00000000000000004"
            )))
            preflight.save_verified_versions(verified, FROZEN_VERSIONS)
            original = verified.read_bytes()
            output = io.StringIO()
            with (
                patch.object(sys, "argv", ["preflight.py", "--versions-file", str(candidate),
                                           "--verified-file", str(verified)]),
                patch.object(preflight.boto3, "Session") as session,
                contextlib.redirect_stdout(output),
            ):
                exit_code = preflight.main()
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "BLOCKED")
            session.assert_not_called()
            self.assertEqual(verified.read_bytes(), original)

    def test_ready_output_is_separate_owner_only_json(self):
        with tempfile.TemporaryDirectory() as directory:
            verified = Path(directory) / "verified.json"
            preflight.save_verified_versions(verified, FROZEN_VERSIONS)
            self.assertEqual(json.loads(verified.read_text()), FROZEN_VERSIONS)
            self.assertEqual(stat.S_IMODE(verified.stat().st_mode), 0o600)
            preflight.save_verified_versions(verified, FROZEN_VERSIONS)
            with self.assertRaisesRegex(preflight.Blocked, "Existing verified pins differ"):
                preflight.save_verified_versions(
                    verified, dict(FROZEN_VERSIONS, relay_ami_id="ami-00000000000000004")
                )
            self.assertEqual(json.loads(verified.read_text()), FROZEN_VERSIONS)

    def test_successful_preflight_records_pair_in_verified_output(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.json"
            verified = Path(directory) / "verified.json"
            candidate.write_text(json.dumps(VERSIONS))
            output = io.StringIO()
            with (
                patch.object(sys, "argv", ["preflight.py", "--versions-file", str(candidate),
                                           "--verified-file", str(verified)]),
                patch.object(preflight.boto3, "Session"),
                patch.object(preflight, "collect", return_value={
                    "status": "READY",
                    "amis": {"node_ami": {"image_id": NODE_AMI}, "node_ssm_parameter_version": 7},
                }),
                contextlib.redirect_stdout(output),
            ):
                exit_code = preflight.main()
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "READY")
            self.assertEqual(json.loads(verified.read_text()), FROZEN_VERSIONS)
            self.assertEqual(stat.S_IMODE(verified.stat().st_mode), 0o600)


class ControllerPolicyTests(unittest.TestCase):
    def test_rendered_inline_policy_fits_role_quota_and_protects_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / "terraform/workload/controller_policy.tf", root / "controller_policy.tf")
            (root / "inputs.tf").write_text(
                'variable "aws_region" { default = "ap-southeast-1" }\n'
                'variable "aws_account_id" { default = "203888389134" }\n'
                'variable "cluster_name" { default = "contact-form-eks" }\n'
                'locals { certificate_arn = "arn:aws:acm:ap-southeast-1:203888389134:certificate/test" }\n'
            )
            result = subprocess.run(
                ["terraform", f"-chdir={root}", "console", "-no-color"],
                input="jsonencode(local.controller_policy)\n", text=True, capture_output=True,
                check=True,
            )
        rendered = json.loads(result.stdout.strip())
        document = json.loads(rendered)
        print(f"controller_inline_policy_chars={len(rendered)}")
        self.assertLessEqual(len(rendered), 10240)
        statements = {item["Sid"]: item for item in document["Statement"]}
        owned = statements["ManageOwnedLoadBalancer"]["Condition"]["StringEquals"]
        self.assertEqual(owned["aws:ResourceTag/elbv2.k8s.aws/cluster"], "contact-form-eks")
        self.assertEqual(owned["aws:ResourceTag/ingress.k8s.aws/stack"], "contact-form/contact-form")
        self.assertEqual(statements["NeverRemoveOwnershipTags"]["Effect"], "Deny")
        self.assertEqual(statements["NeverChangeClusterOwnership"]["Effect"], "Deny")
        self.assertEqual(statements["NeverChangeStackOwnership"]["Effect"], "Deny")
        create_tags = statements["TagResourcesDuringCreation"]["Condition"]["StringEquals"]
        self.assertIn("CreateListener", create_tags["elasticloadbalancing:CreateAction"])
        self.assertIn("CreateRule", create_tags["elasticloadbalancing:CreateAction"])


if __name__ == "__main__":
    unittest.main()
