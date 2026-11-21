import click
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from . import security as sec
from .db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")

@bp.route("/")
@sec.login_required()
def queue():
    if g.user["role"] != "admin": abort(404)
    # Moderators see gig content only. No emails, no payment details, no messages.
    gigs = get_db().execute("SELECT id,title,description,category,price,seller_name,status FROM gigs WHERE status='pending' ORDER BY id").fetchall()
    return render_template("account/admin.html", gigs=gigs)

@bp.route("/gig/<int:gig_id>", methods=["POST"])
@sec.login_required()
def decide(gig_id):
    if g.user["role"] != "admin": abort(404)
    action = request.form.get("action")
    if action not in ("approve", "reject"): abort(400)
    d = get_db()
    d.execute("UPDATE gigs SET status=? WHERE id=? AND status='pending'", ("approved" if action == "approve" else "rejected", gig_id)); d.commit()
    sec.audit("gig_" + action, str(gig_id))
    return redirect(url_for("admin.queue"))

@bp.cli.command("create-admin")
@click.argument("email")
@click.option("--name", default="Admin")
def create_admin(email, name):
    """flask --app wsgi admin create-admin you@example.com  (prompts for password)"""
    pw = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    if (p := sec.password_problem(pw, email)): raise click.ClickException(p)
    email = email.strip().lower(); d = get_db()
    d.execute("INSERT INTO users(email_hash,email_enc,password_hash,display_name,role) VALUES(?,?,?,?, 'admin')",
              (sec.blind_index(email), sec.encrypt(email, "users.email"), sec.hash_password(pw), name)); d.commit()
    click.echo("Admin created.")
