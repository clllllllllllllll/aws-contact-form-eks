# Application scaffold

No form routes, database operations, or secret retrieval are implemented yet.

Intended structure:
- contact_form/ will hold the Flask factory, routes, database access, and Secrets Manager client.
- templates/ and static/ will hold the form UI.
- sql/schema.sql will define the contact submissions table.
- tests/ will cover validation and PostgreSQL persistence.
- Dockerfile will become a non-root Gunicorn image with the RDS CA bundle.

.env.example lists configuration names only. Keep real local values in an ignored .env file.
