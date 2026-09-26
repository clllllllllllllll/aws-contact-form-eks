"""Readback permits only synthetic addresses and never fetches secrets for others."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "show_records.py"
spec = importlib.util.spec_from_file_location("show_records_under_test", SCRIPT)
show_records = importlib.util.module_from_spec(spec)
spec.loader.exec_module(show_records)


def test_readback_rejects_personal_email_before_secret_access(monkeypatch):
    for key, value in {
        "AWS_REGION": "ap-southeast-1",
        "DB_HOST": "example.rds.amazonaws.com",
        "DB_PORT": "5432",
        "DB_NAME": "contactform",
        "DEMO_EMAIL": "person@personal.test",
        "DB_MASTER_SECRET_ARN": "arn:aws:secretsmanager:example",
    }.items():
        monkeypatch.setenv(key, value)
    with patch.object(show_records.boto3, "client") as client:
        with pytest.raises(RuntimeError, match="synthetic"):
            show_records.main()
    client.assert_not_called()
