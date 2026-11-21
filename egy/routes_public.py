import os, re
from flask import Blueprint, abort, current_app, render_template, request, send_from_directory, Response
from .db import get_db
from .constants import CATEGORIES, PAYMENTS

bp = Blueprint("public", __name__)

@bp.route("/")
def home():
    d = get_db()
    stats = {
        "freelancers": d.execute("SELECT COUNT(*) FROM users WHERE role='freelancer'").fetchone()[0],
        "gigs": d.execute("SELECT COUNT(*) FROM gigs WHERE status='approved'").fetchone()[0],
        "works": d.execute("SELECT COUNT(*) FROM portfolio_items").fetchone()[0],
    }
    return render_template("client/home.html", stats=stats)

@bp.route("/explore")
def explore():
    return render_template("client/explore.html")

@bp.route("/why-us")
def why_us():
    return render_template("why_us.html")

@bp.route("/gig/<int:gig_id>")
def gig_detail(gig_id):
    d = get_db()
    gig = d.execute("SELECT * FROM gigs WHERE id=? AND status='approved'", (gig_id,)).fetchone()
    if not gig: return render_template("client/gig_detail.html", gig=None), 404
    pays = [r["method"] for r in d.execute("SELECT method FROM gig_payments WHERE gig_id=?", (gig_id,))]
    works = d.execute("SELECT * FROM portfolio_items WHERE user_id=? ORDER BY id DESC LIMIT 6", (gig["user_id"],)).fetchall() if gig["user_id"] else []
    return render_template("client/gig_detail.html", gig=gig, pays=pays, works=works)

@bp.route("/freelancer/<int:uid>")
def public_profile(uid):
    d = get_db()
    u = d.execute("SELECT id,display_name,bio,created_at FROM users WHERE id=? AND role='freelancer' AND is_active=1", (uid,)).fetchone()
    if not u: abort(404)
    works = d.execute("SELECT * FROM portfolio_items WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    gigs = d.execute("SELECT * FROM gigs WHERE user_id=? AND status='approved' ORDER BY id DESC", (uid,)).fetchall()
    return render_template("freelancer/public_profile.html", u=u, works=works, gigs=gigs)

@bp.route("/media/<name>")
def media(name):
    if not re.fullmatch(r"[0-9a-f]{32}\.webp", name): abort(404)
    r = send_from_directory(current_app.config["UPLOAD_DIR"], name, mimetype="image/webp", max_age=86400)
    r.headers["Content-Disposition"] = "inline"
    return r

@bp.route("/healthz")
def healthz():
    return {"ok": True}

@bp.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /account/\nDisallow: /orders/\nDisallow: /admin/\nDisallow: /api/\n", mimetype="text/plain")
