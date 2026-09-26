"""Offline render check for the ALB access log Ingress annotation."""

import json
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


TEMPLATES = Path(__file__).resolve().parents[2] / "ansible/templates"


class AlbAccessLogRenderTests(unittest.TestCase):
    def test_ingress_uses_workload_bucket_output_and_exact_prefix(self):
        values = {
            "public_subnet_ids": ["subnet-one", "subnet-two"],
            "alb_security_group_id": "sg-example",
            "certificate_arn": "arn:aws:acm:ap-southeast-1:203888389134:certificate/example",
            "alb_access_log_bucket_name": "synthetic-evidence-bucket",
            "domain_name": "example.test",
        }
        tf = {name: {"value": value} for name, value in values.items()}
        environment = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False)
        environment.filters["to_json"] = json.dumps

        manifest = yaml.safe_load(environment.get_template("ingress.yml.j2").render(tf=tf))
        attributes = manifest["metadata"]["annotations"][
            "alb.ingress.kubernetes.io/load-balancer-attributes"
        ]

        self.assertEqual(
            attributes,
            "access_logs.s3.enabled=true,"
            "access_logs.s3.bucket=synthetic-evidence-bucket,"
            "access_logs.s3.prefix=service-logs/alb",
        )


if __name__ == "__main__":
    unittest.main()
