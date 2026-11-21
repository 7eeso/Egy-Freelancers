"""Security primitives: field encryption, password hashing, CSRF, rate limiting, headers, auth guards."""
import base64, hashlib, hmac, os, re, secrets, time
from functools import wraps
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from flask import abort, current_app, g, jsonify, redirect, request, session, url_for
from .db import get_db

_KEYS = {}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,24}$")


# ---------------------------------------------------------------- keys / crypto
def load_dev_keys(app):
    """Development convenience only. Production refuses to start without env keys."""
    kf = Path(app.instance_path) / "dev_keys.txt"
    if not kf.exists():
        kf.write_text(f"{secrets.token_urlsafe(48)}\n{base64.urlsafe_b64encode(os.urandom(32)).decode()}\n")
        os.chmod(kf, 0o600)
    s, m = kf.read_text().split()
    app.config["SECRET_KEY"] = app.config["SECRET_KEY"] or s
    app.config["MASTER_KEY"] = app.config["MASTER_KEY"] or m


def init_crypto(app):
    master = base64.urlsafe_b64decode(app.config["MASTER_KEY"] + "=" * (-len(app.config["MASTER_KEY"]) % 4))
    if len(master) != 32:
        raise RuntimeError("EGY_MASTER_KEY must decode to exactly 32 bytes.")
    def sub(label):  # independent keys per purpose (key separation)
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=label).derive(master)
    _KEYS["enc"], _KEYS["blind"], _KEYS["pepper"] = sub(b"egy-field-enc"), sub(b"egy-blind-index"), sub(b"egy-pw-pepper")


def encrypt(plaintext: str, context: str) -> bytes:
    """AES-256-GCM. `context` is authenticated (AAD) so ciphertext can't be moved between columns."""
    nonce = os.urandom(12)
    return b"\x01" + nonce + AESGCM(_KEYS["enc"]).encrypt(nonce, plaintext.encode(), context.encode())


def decrypt(blob: bytes, context: str) -> str:
    blob = bytes(blob)
    if blob[:1] != b"\x01":
        raise ValueError("unknown ciphertext version")
    return AESGCM(_KEYS["enc"]).decrypt(blob[1:13], blob[13:], context.encode()).decode()


def blind_index(value: str) -> str:
    return hmac.new(_KEYS["blind"], value.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- passwords
_SCRYPT = dict(n=2 ** 15, r=8, p=2, maxmem=128 * 1024 * 1024, dklen=32)


def _pre(password: str) -> bytes:
    return hmac.new(_KEYS["pepper"], password.encode(), hashlib.sha256).digest()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(_pre(password), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        dk = hashlib.scrypt(_pre(password), salt=base64.b64decode(s), **_SCRYPT)
        return hmac.compare_digest(dk, base64.b64decode(h))
    except Exception:
        return False


_DUMMY = None
def dummy_verify(password):  # equalise timing when the account doesn't exist
    global _DUMMY
    _DUMMY = _DUMMY or hash_password("dummy-password")
    verify_password(password, _DUMMY)


COMMON = {"password", "12345678", "123456789", "qwertyuiop", "11111111", "iloveyou", "password1", "00000000", "1q2w3e4r", "egyfreelancers"}
def password_problem(pw: str, email: str = ""):
    if len(pw) < 10: return "Use at least 10 characters."
    if len(pw) > 128: return "Password is too long (max 128)."
    if pw.lower() in COMMON or len(set(pw)) < 5: return "That password is too easy to guess."
    if email and len(email.split("@")[0]) >= 4 and email.split("@")[0].lower() in pw.lower(): return "Don't include your email name in your password."
    if not (any(c.isalpha() for c in pw) and any(c.isdigit() or not c.isalnum() for c in pw)):
        return "Mix letters with numbers or symbols."
    return None


# ---------------------------------------------------------------- rate limiting
def client_ip():
    return request.remote_addr or "?"


def rate_limit(name, limit, per_seconds):
    if current_app.config.get("TESTING_NO_LIMIT"):
        return
    key = hashlib.sha256(f"{name}:{client_ip()}".encode()).hexdigest()
    now, d = int(time.time()), get_db()
    row = d.execute("SELECT count, window_start FROM rate_limits WHERE key=?", (key,)).fetchone()
    if not row or now - row["window_start"] >= per_seconds:
        d.execute("INSERT OR REPLACE INTO rate_limits VALUES(?,?,?)", (key, 1, now)); d.commit(); return
    if row["count"] >= limit:
        retry = per_seconds - (now - row["window_start"])
        resp = jsonify(error="Too many attempts. Please wait a bit and try again.")
        resp.status_code = 429; resp.headers["Retry-After"] = str(max(retry, 1))
        abort(resp)
    d.execute("UPDATE rate_limits SET count=count+1 WHERE key=?", (key,)); d.commit()


def limited(name, limit, per_seconds, count_get=False):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if count_get or request.method not in ("GET", "HEAD"):
                rate_limit(name, limit, per_seconds)
            return f(*a, **k)
        return w
    return deco


# ---------------------------------------------------------------- csrf / session / auth
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def audit(action, detail=""):
    d = get_db()
    d.execute("INSERT INTO audit_log(user_id,action,detail) VALUES(?,?,?)", (g.user["id"] if getattr(g, "user", None) else None, action, detail[:200]))
    d.commit()


def login_user(user_id):
    session.clear()           # prevents session fixation
    session["uid"] = user_id
    session["csrf"] = secrets.token_urlsafe(32)
    session.permanent = True


def login_required(role=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if not g.user:
                if request.path.startswith("/api/"):
                    return jsonify(error="Please log in."), 401
                return redirect(url_for("auth.login", next=request.path))
            if role and g.user["role"] != role and g.user["role"] != "admin":
                abort(403)
            return f(*a, **k)
        return w
    return deco


def init_app(app):
    @app.before_request
    def load_user():
        g.user = None
        uid = session.get("uid")
        if uid:
            u = get_db().execute("SELECT * FROM users WHERE id=? AND is_active=1", (uid,)).fetchone()
            if u: g.user = u
            else: session.clear()

    @app.before_request
    def csrf_and_origin():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                abort(403)
            sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
                if request.path.startswith("/api/"):
                    return jsonify(error="Security token expired. Refresh the page."), 403
                abort(403)

    @app.context_processor
    def inject():
        return {"csrf_token": csrf_token, "current_user": g.get("user")}

    @app.after_request
    def headers(resp):
        h = resp.headers
        h["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                        "media-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; "
                                        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), interest-cohort=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        if app.config["ENV_NAME"] == "production":
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        if g.get("user") or request.path.startswith("/api/") or request.path in ("/login", "/register"):
            h["Cache-Control"] = "no-store"
        h.pop("Server", None)
        return resp

    def err(code, msg):
        def handler(_e):
            if request.path.startswith("/api/"):
                return jsonify(error=msg), code
            from flask import render_template
            return render_template("error.html", code=code, message=msg), code
        return handler
    for c, m in ((400, "Bad request."), (403, "You don't have access to this."), (404, "We couldn't find that page."),
                 (405, "That action isn't allowed here."), (413, "That file is too large (max 6 MB)."), (429, "Too many requests. Slow down a little."),
                 (500, "Something went wrong on our side.")):
        app.register_error_handler(c, err(c, m))
