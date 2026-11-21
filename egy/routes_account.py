import json, os
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from . import security as sec, validators as v
from .constants import CATEGORIES, PAYMENTS
from .db import get_db
from .media import save_image

bp = Blueprint("account", __name__)

ORDER_FLOW = {  # (from_status, actor) -> allowed next statuses
    ("requested", "freelancer"): ("accepted", "declined"),
    ("requested", "client"): ("cancelled",),
    ("accepted", "client"): ("paid_by_client", "cancelled"),
    ("accepted", "freelancer"): ("cancelled",),
    ("paid_by_client", "freelancer"): ("payment_confirmed",),
    ("payment_confirmed", "freelancer"): ("delivered",),
    ("delivered", "client"): ("completed",),
}
LABELS = {"requested": "Waiting for freelancer", "accepted": "Accepted: pay the freelancer directly", "declined": "Declined",
          "paid_by_client": "Client says they paid", "payment_confirmed": "Payment confirmed: work in progress",
          "delivered": "Delivered: awaiting client", "completed": "Completed", "cancelled": "Cancelled"}

def _flash_redirect(msg, endpoint, **kw):
    flash(msg); return redirect(url_for(endpoint, **kw))

# ------------------------------------------------------------------ dashboard
@bp.route("/account")
@sec.login_required()
def dashboard():
    d, u = get_db(), g.user
    col = "freelancer_id" if u["role"] == "freelancer" else "client_id"
    orders = d.execute(f"SELECT o.*, g.title FROM orders o JOIN gigs g ON g.id=o.gig_id WHERE o.{col}=? ORDER BY o.id DESC LIMIT 50", (u["id"],)).fetchall()
    gigs = d.execute("SELECT * FROM gigs WHERE user_id=? ORDER BY id DESC", (u["id"],)).fetchall() if u["role"] == "freelancer" else []
    projects = d.execute("SELECT * FROM projects WHERE client_id=? ORDER BY id DESC", (u["id"],)).fetchall() if u["role"] == "client" else []
    return render_template("account/dashboard.html", orders=orders, gigs=gigs, projects=projects, labels=LABELS)

# ------------------------------------------------------------------ profile, portfolio, payout details
@bp.route("/account/profile", methods=["GET", "POST"])
@sec.login_required()
def profile():
    d, u = get_db(), g.user
    if request.method == "POST":
        try:
            name = v.text(request.form.get("display_name"), "Display name", 2, 60)
            bio = v.text(request.form.get("bio"), "Bio", 0, 600, multiline=True) if request.form.get("bio", "").strip() else ""
        except v.Invalid as e:
            flash(str(e)); return redirect(url_for("account.profile"))
        d.execute("UPDATE users SET display_name=?, bio=? WHERE id=?", (name, bio, u["id"]))
        d.execute("UPDATE gigs SET seller_name=? WHERE user_id=?", (name, u["id"])); d.commit()
        return _flash_redirect("Profile saved.", "account.profile")
    works = d.execute("SELECT * FROM portfolio_items WHERE user_id=? ORDER BY id DESC", (u["id"],)).fetchall()
    methods = {r["method"]: sec.decrypt(r["details_enc"], f"payout.{u['id']}.{r['method']}") for r in
               d.execute("SELECT * FROM payout_methods WHERE user_id=?", (u["id"],))} if u["role"] == "freelancer" else {}
    return render_template("account/profile.html", works=works, methods=methods,
                           email=sec.decrypt(u["email_enc"], "users.email"))

@bp.route("/account/portfolio", methods=["POST"])
@sec.login_required("freelancer")
@sec.limited("portfolio", 20, 3600)
def add_portfolio():
    d, u = get_db(), g.user
    try:
        title = v.text(request.form.get("title"), "Title", 3, 100)
        desc = v.text(request.form.get("description"), "Description", 0, 500, multiline=True) if request.form.get("description", "").strip() else ""
        link = v.url(request.form.get("link_url"), "Link")
        f = request.files.get("image")
        image = save_image(f, current_app.config["UPLOAD_DIR"]) if f and f.filename else None
        if not image and not link: raise v.Invalid("Add an image or a link so clients can see your work.")
        if d.execute("SELECT COUNT(*) FROM portfolio_items WHERE user_id=?", (u["id"],)).fetchone()[0] >= 30: raise v.Invalid("Portfolio limit reached (30 items).")
    except (v.Invalid, ValueError) as e:
        return _flash_redirect(str(e), "account.profile")
    d.execute("INSERT INTO portfolio_items(user_id,title,description,image_file,link_url) VALUES(?,?,?,?,?)", (u["id"], title, desc, image, link or None)); d.commit()
    return _flash_redirect("Work added to your portfolio.", "account.profile")

@bp.route("/account/portfolio/<int:item_id>/delete", methods=["POST"])
@sec.login_required("freelancer")
def delete_portfolio(item_id):
    d = get_db()
    row = d.execute("SELECT * FROM portfolio_items WHERE id=? AND user_id=?", (item_id, g.user["id"])).fetchone()
    if not row: abort(404)
    if row["image_file"]:
        try: os.remove(os.path.join(current_app.config["UPLOAD_DIR"], row["image_file"]))
        except OSError: pass
    d.execute("DELETE FROM portfolio_items WHERE id=?", (item_id,)); d.commit()
    return _flash_redirect("Removed.", "account.profile")

@bp.route("/account/payout", methods=["POST"])
@sec.login_required("freelancer")
@sec.limited("payout", 30, 3600)
def save_payout():
    d, u = get_db(), g.user
    try:
        method = v.choice(request.form.get("method"), "payment method", PAYMENTS)
        raw = request.form.get("details", "").strip()
        if not raw:  # empty = remove
            d.execute("DELETE FROM payout_methods WHERE user_id=? AND method=?", (u["id"], method)); d.commit()
            return _flash_redirect("Payment method removed.", "account.profile")
        details = v.payout(method, raw)
    except v.Invalid as e:
        return _flash_redirect(str(e), "account.profile")
    d.execute("INSERT INTO payout_methods(user_id,method,details_enc) VALUES(?,?,?) ON CONFLICT(user_id,method) DO UPDATE SET details_enc=excluded.details_enc",
              (u["id"], method, sec.encrypt(details, f"payout.{u['id']}.{method}"))); d.commit()
    sec.audit("payout_saved", method)
    return _flash_redirect("Saved. Details are encrypted and only shown to a client after you accept their order.", "account.profile")

# ------------------------------------------------------------------ gigs & projects
@bp.route("/freelancer/post-gig", methods=["GET", "POST"])
@sec.login_required("freelancer")
@sec.limited("post-gig", 15, 3600)
def post_gig():
    d, u = get_db(), g.user
    have = [r["method"] for r in d.execute("SELECT method FROM payout_methods WHERE user_id=?", (u["id"],))]
    if request.method == "GET":
        return render_template("freelancer/post_gig.html", have=have, error=None, form={})
    f = request.form
    try:
        title = v.text(f.get("title"), "Title", 10, 120)
        desc = v.text(f.get("description"), "Description", 30, 2000, multiline=True)
        cat = v.choice(f.get("category"), "category", CATEGORIES)
        price = v.integer(f.get("price"), "Price", 1, 1_000_000)
        pays = [p for p in f.getlist("payments") if p in PAYMENTS]
        if not pays: raise v.Invalid("Choose at least one payment method.")
        missing = [PAYMENTS[p] for p in pays if p not in have]
        if missing: raise v.Invalid("Add your payment details for: " + ", ".join(missing) + " (Profile → Payment details).")
        if d.execute("SELECT COUNT(*) FROM portfolio_items WHERE user_id=?", (u["id"],)).fetchone()[0] < 1:
            raise v.Invalid("Add at least one portfolio item first. Your work is your credential here.")
    except v.Invalid as e:
        return render_template("freelancer/post_gig.html", have=have, error=str(e), form=f), 400
    cur = d.execute("INSERT INTO gigs(user_id,title,description,category,price,seller_name,status) VALUES(?,?,?,?,?,?,'pending')", (u["id"], title, desc, cat, price, u["display_name"]))
    d.executemany("INSERT INTO gig_payments VALUES(?,?)", [(cur.lastrowid, p) for p in pays]); d.commit()
    return _flash_redirect("Submitted! A moderator will review your gig. It goes live once approved.", "account.dashboard")

@bp.route("/post-project", methods=["GET", "POST"])
@sec.login_required("client")
@sec.limited("post-project", 15, 3600)
def post_project():
    if request.method == "GET":
        return render_template("client/post_project.html", error=None, form={})
    f = request.form
    try:
        title = v.text(f.get("title"), "Title", 10, 120)
        desc = v.text(f.get("description"), "Description", 30, 2000, multiline=True)
        cat = v.choice(f.get("category"), "category", CATEGORIES)
        budget = v.integer(f.get("budget"), "Budget", 1, 10_000_000)
    except v.Invalid as e:
        return render_template("client/post_project.html", error=str(e), form=f), 400
    d = get_db()
    d.execute("INSERT INTO projects(client_id,title,description,category,budget) VALUES(?,?,?,?,?)", (g.user["id"], title, desc, cat, budget)); d.commit()
    return _flash_redirect("Project saved. Browse freelancers and request a service to get started.", "account.dashboard")

# ------------------------------------------------------------------ orders (payment is OFF-platform)
@bp.route("/gig/<int:gig_id>/order", methods=["POST"])
@sec.login_required("client")
@sec.limited("order", 20, 3600)
def create_order(gig_id):
    d = get_db()
    gig = d.execute("SELECT * FROM gigs WHERE id=? AND status='approved' AND user_id IS NOT NULL", (gig_id,)).fetchone()
    if not gig: abort(404)
    if gig["user_id"] == g.user["id"]: abort(403)
    try:
        method = v.choice(request.form.get("payment_method"), "payment method", [r["method"] for r in d.execute("SELECT method FROM gig_payments WHERE gig_id=?", (gig_id,))])
        note = v.text(request.form.get("message"), "Message", 5, 1000, multiline=True)
    except v.Invalid as e:
        return _flash_redirect(str(e), "public.gig_detail", gig_id=gig_id)
    if d.execute("SELECT 1 FROM orders WHERE gig_id=? AND client_id=? AND status IN ('requested','accepted','paid_by_client','payment_confirmed','delivered')", (gig_id, g.user["id"])).fetchone():
        return _flash_redirect("You already have an active order for this service.", "public.gig_detail", gig_id=gig_id)
    cur = d.execute("INSERT INTO orders(gig_id,client_id,freelancer_id,payment_method,agreed_price) VALUES(?,?,?,?,?)", (gig_id, g.user["id"], gig["user_id"], method, gig["price"]))
    d.execute("INSERT INTO messages(order_id,sender_id,body_enc) VALUES(?,?,?)", (cur.lastrowid, g.user["id"], sec.encrypt(note, f"msg.{cur.lastrowid}"))); d.commit()
    return redirect(url_for("account.order_view", order_id=cur.lastrowid))

def _order_for_user(order_id):
    o = get_db().execute("SELECT o.*, g.title FROM orders o JOIN gigs g ON g.id=o.gig_id WHERE o.id=?", (order_id,)).fetchone()
    if not o or g.user["id"] not in (o["client_id"], o["freelancer_id"]): abort(404)   # 404, not 403: don't leak existence
    return o

@bp.route("/orders/<int:order_id>")
@sec.login_required()
def order_view(order_id):
    d, o = get_db(), _order_for_user(order_id)
    actor = "client" if g.user["id"] == o["client_id"] else "freelancer"
    msgs = [{"mine": m["sender_id"] == g.user["id"], "at": m["created_at"], "body": sec.decrypt(m["body_enc"], f"msg.{order_id}")}
            for m in d.execute("SELECT * FROM messages WHERE order_id=? ORDER BY id", (order_id,))]
    pay_details = None
    if actor == "client" and o["status"] == "accepted":
        r = d.execute("SELECT details_enc FROM payout_methods WHERE user_id=? AND method=?", (o["freelancer_id"], o["payment_method"])).fetchone()
        if r:
            pay_details = sec.decrypt(r["details_enc"], f"payout.{o['freelancer_id']}.{o['payment_method']}")
            sec.audit("payout_revealed", f"order {order_id}")
    other = d.execute("SELECT display_name FROM users WHERE id=?", (o["freelancer_id"] if actor == "client" else o["client_id"],)).fetchone()
    return render_template("account/order.html", o=o, actor=actor, msgs=msgs, pay_details=pay_details, other=other,
                           actions=ORDER_FLOW.get((o["status"], actor), ()), labels=LABELS)

@bp.route("/orders/<int:order_id>/status", methods=["POST"])
@sec.login_required()
@sec.limited("order-status", 60, 3600)
def order_status(order_id):
    d, o = get_db(), _order_for_user(order_id)
    actor = "client" if g.user["id"] == o["client_id"] else "freelancer"
    new = request.form.get("status", "")
    if new not in ORDER_FLOW.get((o["status"], actor), ()): abort(403)
    d.execute("UPDATE orders SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND status=?", (new, order_id, o["status"]))
    ref = request.form.get("reference", "").strip()
    if new == "paid_by_client" and ref:
        d.execute("INSERT INTO messages(order_id,sender_id,body_enc) VALUES(?,?,?)", (order_id, g.user["id"], sec.encrypt("Payment reference: " + ref[:120], f"msg.{order_id}")))
    d.commit(); sec.audit("order_" + new, f"order {order_id}")
    return redirect(url_for("account.order_view", order_id=order_id))

@bp.route("/orders/<int:order_id>/message", methods=["POST"])
@sec.login_required()
@sec.limited("message", 60, 3600)
def order_message(order_id):
    o = _order_for_user(order_id)
    if o["status"] in ("declined", "cancelled", "completed"): abort(403)
    try: body = v.text(request.form.get("body"), "Message", 1, 1000, multiline=True)
    except v.Invalid as e: return _flash_redirect(str(e), "account.order_view", order_id=order_id)
    d = get_db()
    d.execute("INSERT INTO messages(order_id,sender_id,body_enc) VALUES(?,?,?)", (order_id, g.user["id"], sec.encrypt(body, f"msg.{order_id}"))); d.commit()
    return redirect(url_for("account.order_view", order_id=order_id) + "#end")

# ------------------------------------------------------------------ privacy: export + delete
@bp.route("/account/export")
@sec.login_required()
def export_data():
    d, u = get_db(), g.user
    data = {"email": sec.decrypt(u["email_enc"], "users.email"), "display_name": u["display_name"], "role": u["role"], "bio": u["bio"],
            "gigs": [dict(r) for r in d.execute("SELECT title,description,category,price,status FROM gigs WHERE user_id=?", (u["id"],))]}
    from flask import Response
    return Response(json.dumps(data, indent=2, ensure_ascii=False), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=my-egyfreelancers-data.json"})

@bp.route("/account/delete", methods=["POST"])
@sec.login_required()
@sec.limited("delete-account", 5, 3600)
def delete_account():
    d, u = get_db(), g.user
    if not sec.verify_password(request.form.get("password", ""), u["password_hash"]):
        return _flash_redirect("Wrong password. Account not deleted.", "account.profile")
    if u["role"] == "admin": abort(403)
    for r in d.execute("SELECT image_file FROM portfolio_items WHERE user_id=? AND image_file IS NOT NULL", (u["id"],)).fetchall():
        try: os.remove(os.path.join(current_app.config["UPLOAD_DIR"], r["image_file"]))
        except OSError: pass
    # Anonymise instead of breaking order history for the other party; wipe all personal data.
    d.execute("DELETE FROM payout_methods WHERE user_id=?", (u["id"],))
    d.execute("DELETE FROM portfolio_items WHERE user_id=?", (u["id"],))
    d.execute("UPDATE gigs SET status='removed' WHERE user_id=?", (u["id"],))
    d.execute("UPDATE users SET email_hash=?, email_enc=?, password_hash='!', display_name='Deleted user', bio='', is_active=0 WHERE id=?",
              (f"deleted:{u['id']}", sec.encrypt("deleted", "users.email"), u["id"])); d.commit()
    session.clear()
    return redirect(url_for("public.home"))
