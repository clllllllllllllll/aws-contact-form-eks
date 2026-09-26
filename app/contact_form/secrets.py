"""Load application settings from the local environment or AWS Secrets Manager."""

import json
import os

import boto3


def load_settings():
    environment = os.environ.get("APP_ENV", "local")
    if environment not in ("local", "aws"):
        raise RuntimeError("APP_ENV must be local or aws")
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if environment == "aws":
        if not secret_arn:
            raise RuntimeError("DB_SECRET_ARN is required in AWS mode")
        region = os.environ.get("AWS_REGION", "ap-southeast-1")
        response = boto3.client("secretsmanager", region_name=region).get_secret_value(
            SecretId=secret_arn
        )
        secret = json.loads(response["SecretString"])
        required = ("host", "port", "dbname", "username", "password", "flask_secret_key")
        if not isinstance(secret, dict) or any(not secret.get(key) for key in required):
            raise RuntimeError("Application secret is incomplete")
        return {
            "APP_ENV": "aws",
            "SECRET_KEY": secret["flask_secret_key"],
            "DB_CONNECT": {
                "host": secret["host"],
                "port": int(secret["port"]),
                "dbname": secret["dbname"],
                "user": secret["username"],
                "password": secret["password"],
                "sslmode": "verify-full",
                "sslrootcert": os.environ.get(
                    "RDS_CA_BUNDLE", "/etc/ssl/certs/aws-rds-global-bundle.pem"
                ),
            },
        }

    if secret_arn:
        raise RuntimeError("DB_SECRET_ARN requires APP_ENV=aws")
    database_url = os.environ.get("DATABASE_URL")
    signing_key = os.environ.get("FLASK_SECRET_KEY")
    if not database_url or not signing_key:
        raise RuntimeError("DATABASE_URL and FLASK_SECRET_KEY are required locally")
    return {
        "APP_ENV": "local",
        "SECRET_KEY": signing_key,
        "DATABASE_URL": database_url,
    }
