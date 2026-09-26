FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RDS_CA_BUNDLE=/etc/ssl/certs/aws-rds-global-bundle.pem

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -c "from pathlib import Path; from urllib.request import urlopen; url='https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem'; Path('/etc/ssl/certs/aws-rds-global-bundle.pem').write_bytes(urlopen(url, timeout=30).read())" \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY --chown=10001:10001 . /app

USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--worker-tmp-dir", "/dev/shm", "wsgi:app"]
