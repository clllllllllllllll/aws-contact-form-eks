"""Flask application factory."""

from flask import Flask, render_template, request
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from .routes import bp
from .secrets import load_settings


def create_app(test_config=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.update(load_settings() if test_config is None else test_config)
    app.config["MAX_CONTENT_LENGTH"] = 80 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = app.config.get("APP_ENV") == "aws"

    if app.config.get("APP_ENV") == "aws":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

    CSRFProtect(app)
    app.register_blueprint(bp)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; form-action 'self'; "
            "frame-ancestors 'none'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.errorhandler(CSRFError)
    def invalid_csrf(_error):
        return render_template("error.html", message="Form expired. Reload and try again."), 400

    @app.errorhandler(413)
    def too_large(_error):
        return render_template("error.html", message="Message is too large."), 413

    return app
