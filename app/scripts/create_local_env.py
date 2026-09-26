"""Create ignored, local-only development settings without printing credentials."""

import os
import secrets
from pathlib import Path


def main():
    env_file = Path(__file__).resolve().parents[1] / ".env"
    password = secrets.token_hex(24)
    signing_key = secrets.token_hex(32)
    database_url = f"postgresql://contact_local:{password}@127.0.0.1:5432/contact_local"
    settings = {
        "APP_ENV": "local",
        "POSTGRES_USER": "contact_local",
        "POSTGRES_DB": "contact_local",
        "POSTGRES_PASSWORD": password,
        "DATABASE_URL": database_url,
        "TEST_DATABASE_URL": database_url,
        "FLASK_SECRET_KEY": signing_key,
    }
    try:
        fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print("Local .env already exists; leaving it unchanged.")
        return
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        for key, value in settings.items():
            output.write(f"{key}={value}\n")
    print("Created app/.env with local-only credentials (permissions 0600).")


if __name__ == "__main__":
    main()
