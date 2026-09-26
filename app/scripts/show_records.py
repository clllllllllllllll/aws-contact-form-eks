"""Show synthetic contact-form submissions through a short-lived setup-role Job."""

import json
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import psycopg


def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main():
    region = required("AWS_REGION")
    host = required("DB_HOST")
    port = int(required("DB_PORT"))
    dbname = required("DB_NAME")
    email = required("DEMO_EMAIL")
    if len(email) > 254 or not email.lower().endswith("@example.com"):
        raise RuntimeError("DEMO_EMAIL must be a synthetic @example.com address")

    client = boto3.client("secretsmanager", region_name=region)
    master = json.loads(
        client.get_secret_value(SecretId=required("DB_MASTER_SECRET_ARN"))["SecretString"]
    )
    with psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=master["username"],
        password=master["password"],
        sslmode="verify-full",
        sslrootcert=os.environ.get(
            "RDS_CA_BUNDLE", "/etc/ssl/certs/aws-rds-global-bundle.pem"
        ),
        connect_timeout=10,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, email, message, created_at "
                "FROM contact_submissions WHERE email = %s "
                "ORDER BY id DESC LIMIT 5",
                (email,),
            )
            rows = [
                {
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "message": row[3],
                    "created_at": row[4].isoformat(),
                }
                for row in cursor.fetchall()
            ]
    if not rows:
        raise RuntimeError("No contact submissions match the demo email")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (BotoCoreError, ClientError, KeyError, psycopg.Error, RuntimeError, ValueError) as error:
        print(f"Readback failed: {error}", file=sys.stderr)
        sys.exit(1)
