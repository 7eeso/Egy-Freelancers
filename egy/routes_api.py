from flask import Blueprint, jsonify, request
from . import security as sec
from .constants import CATEGORIES
from .db import get_db

bp = Blueprint("api", __name__, url_prefix="/api")

@bp.route("/gigs")
@sec.limited("api-gigs", 120, 60, count_get=True)
def gigs():
    search = request.args.get("search", "").strip()[:80]
    category = request.args.get("category", "").strip()
    sql, args = "SELECT id,user_id,title,description,category,price,seller_name,is_demo FROM gigs WHERE status='approved'", []
    if category:
        if category not in CATEGORIES: return jsonify(error="Unknown category"), 400
        sql += " AND category=?"; args.append(category)
    if search:
        esc = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql += " AND (title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR seller_name LIKE ? ESCAPE '\\')"
        args += [f"%{esc}%"] * 3
    sql += " ORDER BY id DESC LIMIT 60"
    return jsonify(gigs=[dict(r) for r in get_db().execute(sql, args)])
