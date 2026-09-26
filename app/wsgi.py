"""WSGI entry point for Gunicorn."""

from contact_form import create_app

app = create_app()
