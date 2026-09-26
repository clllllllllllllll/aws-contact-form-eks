SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

.PHONY: help setup db test build app check records down

help:
	@printf '%s\n' \
	  'make setup  - create ignored local settings and install Python dependencies' \
	  'make db     - start disposable local PostgreSQL' \
	  'make test   - apply schema and run local integration tests' \
	  'make build  - build the Flask Docker image' \
	  'make app    - apply schema and start the Flask container' \
	  'make check  - check health, image user, and database row count' \
	  'make records - show the five newest local submissions' \
	  'make down   - stop local containers and remove their network'

setup:
	@python3 scripts/create_local_env.py
	if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
	.venv/bin/python -m pip install --no-cache-dir -r requirements-dev.txt

db:
	@python3 scripts/create_local_env.py
	set -a
	. ./.env
	set +a
	if ! docker network inspect contact-form-local >/dev/null 2>&1; then
	  docker network create contact-form-local
	fi
	if ! docker container inspect contact-form-local-db >/dev/null 2>&1; then
	  docker run --rm -d --name contact-form-local-db \
	    --network contact-form-local --publish 127.0.0.1:5432:5432 \
	    --env POSTGRES_USER --env POSTGRES_PASSWORD --env POSTGRES_DB postgres:16
	fi
	for attempt in {1..30}; do
	  if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
	    pg_isready -h 127.0.0.1 -p 5432
	    exit 0
	  fi
	  sleep 1
	done
	pg_isready -h 127.0.0.1 -p 5432

test: db
	@set -a
	. ./.env
	set +a
	PGPASSWORD="$$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$$POSTGRES_USER" \
	  -d "$$POSTGRES_DB" -v ON_ERROR_STOP=1 -f sql/schema.sql
	.venv/bin/python -m pytest -q tests

build:
	@docker build --tag contact-form:local .

app: db
	@set -a
	. ./.env
	set +a
	if ! docker image inspect contact-form:local >/dev/null 2>&1; then
	  printf '%s\n' 'Run make build first.' >&2
	  exit 1
	fi
	PGPASSWORD="$$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$$POSTGRES_USER" \
	  -d "$$POSTGRES_DB" -v ON_ERROR_STOP=1 -f sql/schema.sql
	if ! docker container inspect contact-form-local-app >/dev/null 2>&1; then
	  export DATABASE_URL="postgresql://$${POSTGRES_USER}:$${POSTGRES_PASSWORD}@contact-form-local-db:5432/$${POSTGRES_DB}"
	  docker run --rm -d --name contact-form-local-app \
	    --network contact-form-local --publish 127.0.0.1:8000:8000 \
	    --env DATABASE_URL --env FLASK_SECRET_KEY contact-form:local
	fi

check:
	@curl --fail --silent --show-error http://127.0.0.1:8000/health/live
	printf '\n'
	curl --fail --silent --show-error http://127.0.0.1:8000/health/ready
	printf '\n'
	docker image inspect contact-form:local --format 'image user={{.Config.User}}'
	set -a
	. ./.env
	set +a
	PGPASSWORD="$$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$$POSTGRES_USER" \
	  -d "$$POSTGRES_DB" -tAc 'SELECT count(*) FROM contact_submissions'

records:
	@set -a
	. ./.env
	set +a
	PGPASSWORD="$$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$$POSTGRES_USER" \
	  -d "$$POSTGRES_DB" -c 'SELECT id, name, email, message, created_at FROM contact_submissions ORDER BY id DESC LIMIT 5'

down:
	@for container in contact-form-local-app contact-form-local-db; do
	  if docker container inspect "$$container" >/dev/null 2>&1; then
	    docker stop "$$container"
	  fi
	done
	if docker network inspect contact-form-local >/dev/null 2>&1; then
	  docker network rm contact-form-local
	fi
