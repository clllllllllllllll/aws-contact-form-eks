"""Short-lived PostgreSQL connections keep requests recoverable after failover."""

import psycopg
from flask import current_app


def connect():
    database_url = current_app.config.get("DATABASE_URL")
    if database_url:
        return psycopg.connect(database_url, connect_timeout=5)
    return psycopg.connect(**current_app.config["DB_CONNECT"], connect_timeout=5)


def save_submission(name, email, message):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO contact_submissions (name, email, message) "
                "VALUES (%s, %s, %s)",
                (name, email, message),
            )


def database_ready():
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone()[0] == 1
    except psycopg.Error:
        return False
