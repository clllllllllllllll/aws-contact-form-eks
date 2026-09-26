"""Local safety checks for deployment helper output, DNS cleanup and API TLS."""

import base64
import contextlib
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import manage_alb, open_tunnel, publish_image


class FakeRoute53:
    def __init__(self, record):
        self.record = record
        self.changes = []

    def list_resource_record_sets(self, **_):
        return {"ResourceRecordSets": [self.record] if self.record else []}

    def change_resource_record_sets(self, **arguments):
        self.changes.append(arguments)
        return {"ChangeInfo": {"Id": "change-1"}}

    def get_waiter(self, _):
        return self

    def wait(self, **_):
        pass


ALB = {
    "DNSName": "k8s-contact-form.example.elb.amazonaws.com",
    "CanonicalHostedZoneId": "ZALB",
}
CREATE_ARGS = type("Arguments", (), {
    "action": "create",
    "zone_id": "ZHOSTED",
    "domain": "example.test",
    "dns_name": ALB["DNSName"],
})()
REMOVE_ARGS = type("Arguments", (), {
    "action": "remove",
    "zone_id": "ZHOSTED",
    "domain": "example.test",
})()


def alias_record(dns_name=ALB["DNSName"], zone_id="ZALB"):
    return {
        "Name": "example.test.",
        "Type": "A",
        "AliasTarget": {
            "DNSName": dns_name + ".",
            "HostedZoneId": zone_id,
            "EvaluateTargetHealth": True,
        },
    }


class DeploymentHelperTests(unittest.TestCase):
    def test_repeated_alias_create_accepts_route53_trailing_dot(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "alb-alias.json"
            route53 = FakeRoute53(alias_record())
            with (
                patch.object(manage_alb, "ALIAS_RECORD_PATH", marker),
                patch.object(manage_alb, "owned_balancers", return_value=[ALB]),
            ):
                changed = manage_alb.update_alias(CREATE_ARGS, object(), route53)
            self.assertFalse(changed)
            self.assertEqual(route53.changes, [])
            self.assertTrue(marker.exists())
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)

    def test_cleanup_refuses_to_delete_an_unrelated_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "alb-alias.json"
            route53 = FakeRoute53(alias_record("portfolio.example.elb.amazonaws.com", "ZOTHER"))
            with (
                patch.object(manage_alb, "ALIAS_RECORD_PATH", marker),
                patch.object(manage_alb, "owned_balancers", return_value=[ALB]),
            ):
                manage_alb.save_alias_record(CREATE_ARGS, ALB)
                with self.assertRaisesRegex(RuntimeError, "does not point"):
                    manage_alb.update_alias(REMOVE_ARGS, object(), route53)
            self.assertEqual(route53.changes, [])

    def test_cleanup_uses_saved_owner_after_alb_disappears(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "alb-alias.json"
            route53 = FakeRoute53(alias_record())
            with (
                patch.object(manage_alb, "ALIAS_RECORD_PATH", marker),
                patch.object(manage_alb, "owned_balancers", return_value=[]),
            ):
                manage_alb.save_alias_record(CREATE_ARGS, ALB)
                changed = manage_alb.update_alias(REMOVE_ARGS, object(), route53)
            self.assertTrue(changed)
            self.assertEqual(route53.changes[0]["ChangeBatch"]["Changes"][0]["Action"], "DELETE")
            self.assertFalse(marker.exists())

    def test_kubeconfig_keeps_original_hostname_and_ca_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(open_tunnel, "ROOT", Path(temporary)):
                path, hostname = open_tunnel.write_kubeconfig({
                    "cluster_endpoint": "https://ABC.eks.amazonaws.com",
                    "cluster_name": "contact-form-eks",
                    "cluster_ca_data": "ZmFrZS1jYQ==",
                }, "contact-form-deployer", 8443)
                cluster = json.loads(path.read_text())["clusters"][0]["cluster"]
                self.assertEqual(hostname, "abc.eks.amazonaws.com")
                self.assertEqual(cluster["tls-server-name"], hostname)
                self.assertEqual(cluster["server"], "https://127.0.0.1:8443")
                self.assertEqual(cluster["certificate-authority-data"], "ZmFrZS1jYQ==")
                self.assertNotIn("insecure-skip-tls-verify", cluster)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_first_image_publication_returns_only_json_on_stdout(self):
        digest = "sha256:" + "b" * 64
        fake_client = Mock()
        fake_client.get_authorization_token.return_value = {
            "authorizationData": [{
                "authorizationToken": base64.b64encode(b"AWS:test-token").decode(),
            }],
        }
        fake_session = Mock()
        fake_session.client.return_value = fake_client

        def docker_run(command, **kwargs):
            if command[1] in ("build", "push"):
                print("Docker progress", file=kwargs.get("stdout", sys.stdout))
            return subprocess.CompletedProcess(command, 0)

        output = io.StringIO()
        errors = io.StringIO()
        with (
            patch.object(publish_image.boto3, "Session", return_value=fake_session),
            patch.object(publish_image, "image_tag", return_value="a1b2c3d4e5f6"),
            patch.object(publish_image, "image_digest", side_effect=[None, digest]),
            patch.object(publish_image.subprocess, "run", side_effect=docker_run),
            patch.object(sys, "argv", [
                "publish_image.py", "--repository-url",
                "203888389134.dkr.ecr.ap-southeast-1.amazonaws.com/contact-form",
            ]),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
        ):
            publish_image.main()
        result = json.loads(output.getvalue())
        self.assertTrue(result["published"])
        self.assertTrue(result["image_uri"].endswith("@" + digest))
        self.assertIn("Docker progress", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
