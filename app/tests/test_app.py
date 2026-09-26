"""Integration checks against a disposable local PostgreSQL database."""

import os
import secrets
from html.parser import HTMLParser
from pathlib import Path

import psycopg
import pytest

from contact_form import create_app


class CsrfParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            fields = dict(attrs)
            if fields.get("name") == "csrf_token":
                self.token = fields.get("value")


def csrf_token(client):
    response = client.get("/")
    assert response.status_code == 200
    parser = CsrfParser()
    parser.feed(response.get_data(as_text=True))
    assert parser.token
    return parser.token


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL integration tests")
    schema = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
    with psycopg.connect(url) as connection:
        connection.execute(schema.read_text())
    return url


@pytest.fixture
def client(database_url):
    with psycopg.connect(database_url) as connection:
        connection.execute("TRUNCATE contact_submissions RESTART IDENTITY")
    application = create_app(
        {
            "TESTING": True,
            "APP_ENV": "local",
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_URL": database_url,
        }
    )
    return application.test_client()


def test_submission_persists_without_interpreting_sql(client, database_url):
    message = "Please call me; '); DROP TABLE contact_submissions; --"
    response = client.post(
        "/",
        data={
            "csrf_token": csrf_token(client),
            "name": "Demo Person",
            "email": "demo@example.com",
            "message": message,
        },
    )
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/thanks")
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            "SELECT name, email, message FROM contact_submissions WHERE email = %s",
            ("demo@example.com",),
        ).fetchone()
    assert row == ("Demo Person", "demo@example.com", message)


@pytest.mark.parametrize(
    "name,email,message",
    [
        ("", "demo@example.com", "Hello"),
        ("Demo", "bad-address", "Hello"),
        ("Demo", "demo@example.com", " " * 10),
        ("Demo", "demo@example.com", "x" * 5001),
    ],
)
def test_invalid_form_does_not_write(client, database_url, name, email, message):
    response = client.post(
        "/",
        data={
            "csrf_token": csrf_token(client),
            "name": name,
            "email": email,
            "message": message,
        },
    )
    assert response.status_code == 400
    with psycopg.connect(database_url) as connection:
        count = connection.execute("SELECT count(*) FROM contact_submissions").fetchone()[0]
    assert count == 0


def test_missing_csrf_is_rejected(client, database_url):
    response = client.post(
        "/",
        data={"name": "Demo", "email": "demo@example.com", "message": "Hello"},
    )
    assert response.status_code == 400
    with psycopg.connect(database_url) as connection:
        count = connection.execute("SELECT count(*) FROM contact_submissions").fetchone()[0]
    assert count == 0


def test_database_outage_fails_readiness_but_not_liveness():
    application = create_app(
        {
            "TESTING": True,
            "APP_ENV": "local",
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_URL": "postgresql://unused:unused@127.0.0.1:1/unused",
        }
    )
    client = application.test_client()
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    response = client.post(
        "/",
        data={
            "csrf_token": csrf_token(client),
            "name": "Demo",
            "email": "demo@example.com",
            "message": "Hello",
        },
    )
    assert response.status_code == 503
    assert b"Message could not be saved" in response.data


def test_maximum_unicode_message_is_saved(client, database_url):
    message = "😀" * 5000
    response = client.post(
        "/",
        data={
            "csrf_token": csrf_token(client),
            "name": "Demo Person",
            "email": "demo@example.com",
            "message": message,
        },
    )
    assert response.status_code == 303
    with psycopg.connect(database_url) as connection:
        saved = connection.execute("SELECT message FROM contact_submissions").fetchone()[0]
    assert saved == message


def test_readiness_recovers_when_database_is_available(client, database_url):
    application = client.application
    application.config["DATABASE_URL"] = "postgresql://unused:unused@127.0.0.1:1/unused"
    assert client.get("/health/ready").status_code == 503
    application.config["DATABASE_URL"] = database_url
    assert client.get("/health/ready").status_code == 200


def test_invalid_input_is_escaped(client):
    response = client.post(
        "/",
        data={
            "csrf_token": csrf_token(client),
            "name": "<script>alert(1)</script>",
            "email": "not-an-email",
            "message": "Hello",
        },
    )
    assert response.status_code == 400
    assert b"&lt;script&gt;" in response.data
    assert b"<script>" not in response.data


def test_aws_mode_requires_secret_arn(monkeypatch):
    from contact_form.secrets import load_settings

    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://local-only@example.invalid/local")
    monkeypatch.setenv("FLASK_SECRET_KEY", "local-only")
    with pytest.raises(RuntimeError, match="DB_SECRET_ARN is required"):
        load_settings()


def test_aws_secret_enforces_verified_tls(monkeypatch):
    import json

    from contact_form.secrets import load_settings

    secret_arn = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:test"
    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.setenv("DB_SECRET_ARN", secret_arn)
    monkeypatch.delenv("RDS_CA_BUNDLE", raising=False)

    class FakeClient:
        def get_secret_value(self, SecretId):
            assert SecretId == secret_arn
            return {
                "SecretString": json.dumps(
                    {
                        "host": "db.example.invalid",
                        "port": 5432,
                        "dbname": "contact",
                        "username": "app",
                        "password": "test-only-password",
                        "flask_secret_key": "test-only-signing-key",
                    }
                )
            }

    def fake_client(service_name, region_name):
        assert service_name == "secretsmanager"
        assert region_name == "ap-southeast-1"
        return FakeClient()

    monkeypatch.setattr("contact_form.secrets.boto3.client", fake_client)
    settings = load_settings()
    assert settings["APP_ENV"] == "aws"
    assert settings["DB_CONNECT"]["sslmode"] == "verify-full"
    assert settings["DB_CONNECT"]["sslrootcert"].endswith("aws-rds-global-bundle.pem")


def test_incomplete_aws_secret_is_rejected(monkeypatch):
    from contact_form.secrets import load_settings

    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:test")

    class FakeClient:
        def get_secret_value(self, SecretId):
            return {"SecretString": '{"host":"db.example.invalid"}'}

    monkeypatch.setattr("contact_form.secrets.boto3.client", lambda *args, **kwargs: FakeClient())
    with pytest.raises(RuntimeError, match="Application secret is incomplete"):
        load_settings()
