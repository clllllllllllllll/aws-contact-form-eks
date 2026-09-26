"""Contact form and Kubernetes health endpoints."""

import psycopg
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.fields import EmailField
from wtforms.validators import DataRequired, Email, Length

from .db import database_ready, save_submission

bp = Blueprint("contact", __name__)


def strip_value(value):
    return value.strip() if value else value


class ContactForm(FlaskForm):
    name = StringField(
        "Name", filters=[strip_value], validators=[DataRequired(), Length(max=100)]
    )
    email = EmailField(
        "Email",
        filters=[strip_value],
        validators=[DataRequired(), Email(), Length(max=254)],
    )
    message = TextAreaField(
        "Message", filters=[strip_value], validators=[DataRequired(), Length(max=5000)]
    )
    submit = SubmitField("Send message")


@bp.route("/", methods=["GET", "POST"])
def index():
    form = ContactForm()
    if form.validate_on_submit():
        try:
            save_submission(form.name.data, form.email.data, form.message.data)
        except psycopg.Error:
            current_app.logger.error("Database insert failed")
            return render_template(
                "index.html", form=form, error="Message could not be saved. Please try again."
            ), 503
        return redirect(url_for("contact.thanks"), code=303)
    status = 400 if request.method == "POST" else 200
    return render_template("index.html", form=form), status


@bp.get("/thanks")
def thanks():
    return render_template("thanks.html")


@bp.get("/health/live")
def live():
    return jsonify(status="ok")


@bp.get("/health/ready")
def ready():
    if database_ready():
        return jsonify(status="ok")
    return jsonify(status="unavailable"), 503
