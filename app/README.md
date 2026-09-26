# Contact form application

Flask serves a name, email, and message form. PostgreSQL stores submissions in `contact_submissions`. The application has separate liveness (`/health/live`) and database readiness (`/health/ready`) endpoints. Form posts use CSRF protection and parameterized SQL; database errors return a generic message.

## Short rehearsal commands

From this directory, use `make setup` once, then `make db`, `make test`, `make build`, `make app`, and `make check`. Open `http://127.0.0.1:8000/` to submit a sample form; `make check` shows the row count and `make records` shows the five newest submissions. Run `make down` when finished. `make help` lists the commands. All targets use only local Docker and PostgreSQL; none contact AWS.

The [Makefile](Makefile) contains the exact Docker, PostgreSQL, and test commands. During the demo, you can keep this runbook open and explain what each target runs. For example, `make -n build` prints the underlying build command without executing it.

## Run and test locally from WSL

Run these commands from the `app` directory. They use Docker on your workstation and create no AWS resources.

```bash
cd /home/limch/projects/aws-contact-form-eks/app
python3 scripts/create_local_env.py
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements-dev.txt
set -a
. ./.env
set +a
docker network create contact-form-local
docker run --rm -d --name contact-form-local-db \
  --network contact-form-local --publish 127.0.0.1:5432:5432 \
  --env POSTGRES_USER --env POSTGRES_PASSWORD --env POSTGRES_DB postgres:16
pg_isready -h 127.0.0.1 -p 5432
PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" -f sql/schema.sql
.venv/bin/python -m pytest -q tests
```

`create_local_env.py` creates `app/.env` only when absent, with random local credentials and file permissions `0600`. The file is ignored by Git and Docker. `pg_isready` may need a few seconds immediately after the first image pull. The tests initialize the schema if needed and check persistence, validation, CSRF, readiness, and AWS configuration without contacting AWS.

Build and start the same application image used for deployment:

```bash
docker build --tag contact-form:local .
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@contact-form-local-db:5432/${POSTGRES_DB}"
docker run --rm -d --name contact-form-local-app \
  --network contact-form-local --publish 127.0.0.1:8000:8000 \
  --env DATABASE_URL --env FLASK_SECRET_KEY contact-form:local
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

Open `http://127.0.0.1:8000/`, submit a sample form, then query the local database:

```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" -c 'SELECT id, name, email, created_at FROM contact_submissions ORDER BY id DESC LIMIT 5;'
```

The container runs Gunicorn as UID/GID 10001. In AWS mode, set `APP_ENV=aws`, `DB_SECRET_ARN`, and `AWS_REGION`. The pod's IAM role must permit reading only the application secret. The secret JSON requires `host`, `port`, `dbname`, `username`, `password`, and `flask_secret_key`. PostgreSQL connections use the bundled RDS CA and `sslmode=verify-full`. Each Gunicorn worker reads the secret at startup, so credential rotation requires a pod rollout.

Stop the disposable containers and network after the rehearsal:

```bash
docker stop contact-form-local-app contact-form-local-db
docker network rm contact-form-local
unset DATABASE_URL TEST_DATABASE_URL FLASK_SECRET_KEY POSTGRES_PASSWORD
```

The tagged `postgres:16` and `contact-form:local` images remain cached for the next rehearsal. Remove either image with `docker image rm` when it is no longer needed.
