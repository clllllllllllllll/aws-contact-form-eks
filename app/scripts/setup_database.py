"""Initialize a dedicated RDS database without placing passwords in IaC state.

A short-lived Kubernetes Job runs this with its own IRSA service account.
Reruns retain the existing application credential, table, and all rows.
"""

import json
import os
import secrets
from pathlib import Path

import boto3
import psycopg
from psycopg import sql

APP_USER = "contact_app"
LOCK_KEY = 7381051942
CA_BUNDLE = os.environ.get("RDS_CA_BUNDLE", "/etc/ssl/certs/aws-rds-global-bundle.pem")


def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def existing_or_new_app_secret(client, arn, host, port, dbname):
    versions = client.list_secret_version_ids(SecretId=arn)["Versions"]
    has_current = any("AWSCURRENT" in item.get("VersionStages", []) for item in versions)
    if has_current:
        secret = json.loads(client.get_secret_value(SecretId=arn)["SecretString"])
        expected = ("host", "port", "dbname", "username", "password", "flask_secret_key")
        if any(not secret.get(key) for key in expected):
            raise RuntimeError("Existing application secret is incomplete")
        if (secret["host"], str(secret["port"]), secret["dbname"], secret["username"]) != (
            host,
            str(port),
            dbname,
            APP_USER,
        ):
            raise RuntimeError("Existing application secret targets a different database")
        return secret, False

    return {
        "host": host,
        "port": int(port),
        "dbname": dbname,
        "username": APP_USER,
        "password": secrets.token_urlsafe(36),
        "flask_secret_key": secrets.token_urlsafe(48),
    }, True


def initialize(client, connection, app_arn, host, port, dbname):
    # A session advisory lock serializes all setup Jobs, including the
    # Secrets Manager read and write. Closing the connection releases it.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
    try:
        app, needs_write = existing_or_new_app_secret(client, app_arn, host, port, dbname)
        with connection.cursor() as cursor:
            cursor.execute(Path("/app/sql/schema.sql").read_text())
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute("REVOKE ALL ON TABLE contact_submissions FROM PUBLIC")
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_USER,))
            if cursor.fetchone():
                cursor.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(APP_USER), sql.Literal(app["password"])
                    )
                )
            else:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(APP_USER), sql.Literal(app["password"])
                    )
                )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(dbname), sql.Identifier(APP_USER)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(APP_USER))
            )
            cursor.execute(
                sql.SQL("GRANT INSERT ON TABLE contact_submissions TO {}").format(
                    sql.Identifier(APP_USER)
                )
            )
        if needs_write:
            client.put_secret_value(SecretId=app_arn, SecretString=json.dumps(app))
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def main():
    region = required("AWS_REGION")
    host = required("DB_HOST")
    port = int(required("DB_PORT"))
    dbname = required("DB_NAME")
    master_arn = required("DB_MASTER_SECRET_ARN")
    app_arn = required("APP_SECRET_ARN")

    client = boto3.client("secretsmanager", region_name=region)
    master = json.loads(client.get_secret_value(SecretId=master_arn)["SecretString"])
    with psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=master["username"],
        password=master["password"],
        sslmode="verify-full",
        sslrootcert=CA_BUNDLE,
        connect_timeout=10,
        autocommit=True,
    ) as connection:
        initialize(client, connection, app_arn, host, port, dbname)
    print("Database schema and restricted application user are ready.")


if __name__ == "__main__":
    main()
