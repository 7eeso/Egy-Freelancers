import time
from flask import Blueprint, redirect, render_template, request, session, url_for, g
from . import security as sec, validators as v
from .db import get_db

bp = Blueprint("auth", __name__)
LOCK_AFTER, LOCK_SECONDS = 5, 15 * 60

def _safe_next(n):
    return n if n and n.startswith("/") and not n.startswith("//") and "\\" not in n else None

@bp.route("/register", methods=["GET", "POST"])
@sec.limited("register", 8, 3600)
def register():
    if request.method == "GET":
        return render_template("auth/register.html", form={}, error=None)
    f = request.form
    try:
        name = v.text(f.get("display_name"), "Display name", 2, 60)
        email = v.text(f.get("email"), "Email", 5, 254).lower()
        if not sec.EMAIL_RE.fullmatch(email): raise v.Invalid("Enter a valid email address.")
        role = v.choice(f.get("role"), "account type", ("client", "freelancer"))
        pw = f.get("password", "")
        if pw != f.get("password2", ""): raise v.Invalid("Passwords don't match.")
        if (p := sec.password_problem(pw, email)): raise v.Invalid(p)
        if not f.get("terms"): raise v.Invalid("Please accept the terms to continue.")
    except v.Invalid as e:
        return render_template("auth/register.html", form={"display_name": f.get("display_name", ""), "role": f.get("role")}, error=str(e)), 400
    d = get_db()
    try:
        cur = d.execute("INSERT INTO users(email_hash,email_enc,password_hash,display_name,role) VALUES(?,?,?,?,?)",
                        (sec.blind_index(email), sec.encrypt(email, "users.email"), sec.hash_password(pw), name, role))
        d.commit()
    except Exception:
        # Same response whether or not the email exists: no account enumeration.
        sec.dummy_verify(pw)
        return render_template("auth/register.html", form={"display_name": name, "role": role},
                               error="We couldn't create that account. If you already registered, try logging in."), 400
    sec.login_user(cur.lastrowid); g.user = d.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    sec.audit("register", role)
    return redirect(url_for("account.dashboard"))

@bp.route("/login", methods=["GET", "POST"])
@sec.limited("login", 20, 900)
def login():
    nxt = _safe_next(request.args.get("next") or request.form.get("next"))
    if request.method == "GET":
        return render_template("auth/login.html", error=None, next=nxt)
    email = (request.form.get("email") or "").strip().lower()[:254]
    pw = (request.form.get("password") or "")[:200]
    d, now = get_db(), int(time.time())
    u = d.execute("SELECT * FROM users WHERE email_hash=? AND is_active=1", (sec.blind_index(email),)).fetchone()
    generic = "Incorrect email or password."
    if not u:
        sec.dummy_verify(pw)
        return render_template("auth/login.html", error=generic, next=nxt), 401
    if u["locked_until"] > now:
        sec.dummy_verify(pw)
        return render_template("auth/login.html", error="Too many failed attempts. Try again in a few minutes.", next=nxt), 429
    if not sec.verify_password(pw, u["password_hash"]):
        fails = u["failed_logins"] + 1
        d.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (0 if fails >= LOCK_AFTER else fails, now + LOCK_SECONDS if fails >= LOCK_AFTER else 0, u["id"])); d.commit()
        return render_template("auth/login.html", error=generic, next=nxt), 401
    d.execute("UPDATE users SET failed_logins=0, locked_until=0 WHERE id=?", (u["id"],)); d.commit()
    sec.login_user(u["id"]); g.user = u; sec.audit("login")
    return redirect(nxt or url_for("account.dashboard"))

@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("public.home"))
