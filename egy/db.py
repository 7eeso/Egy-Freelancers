import sqlite3
from flask import current_app, g

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 email_hash TEXT NOT NULL UNIQUE,          -- HMAC blind index (lookup only)
 email_enc BLOB NOT NULL,                  -- AES-256-GCM encrypted
 password_hash TEXT NOT NULL,              -- scrypt, per-user salt
 display_name TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('client','freelancer','admin')),
 bio TEXT NOT NULL DEFAULT '',
 failed_logins INTEGER NOT NULL DEFAULT 0,
 locked_until INTEGER NOT NULL DEFAULT 0,
 is_active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS payout_methods(    -- freelancer payment details, encrypted
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 method TEXT NOT NULL,
 details_enc BLOB NOT NULL,
 UNIQUE(user_id, method)
);
CREATE TABLE IF NOT EXISTS gigs(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
 price INTEGER NOT NULL CHECK(price > 0),
 seller_name TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending',
 is_demo INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS gigs_status_idx ON gigs(status);
CREATE INDEX IF NOT EXISTS gigs_cat_idx ON gigs(category);
CREATE TABLE IF NOT EXISTS gig_payments(      -- which methods a gig accepts
 gig_id INTEGER NOT NULL REFERENCES gigs(id) ON DELETE CASCADE,
 method TEXT NOT NULL, PRIMARY KEY(gig_id, method)
);
CREATE TABLE IF NOT EXISTS portfolio_items(   -- proof of work instead of certificates
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 image_file TEXT, link_url TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS projects(          -- client job posts
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 client_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
 budget INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS orders(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 gig_id INTEGER NOT NULL REFERENCES gigs(id),
 client_id INTEGER NOT NULL REFERENCES users(id),
 freelancer_id INTEGER NOT NULL REFERENCES users(id),
 payment_method TEXT, agreed_price INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'requested',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS messages(          -- encrypted at rest
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
 sender_id INTEGER NOT NULL REFERENCES users(id),
 body_enc BLOB NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log(         -- no PII, ever
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rate_limits(
 key TEXT PRIMARY KEY, count INTEGER NOT NULL, window_start INTEGER NOT NULL
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB_PATH"], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


def close_db(_e=None):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def init_db():
    d = get_db()
    d.executescript(SCHEMA)
    d.commit()
    seed_demo(d)


def seed_demo(d):
    if d.execute("SELECT COUNT(*) FROM gigs").fetchone()[0]:
        return
    demos = [
        ("I will design a clean brand identity", "A logo, color palette and starter brand guide for your business.", "design", 850, "Mariam", ["instapay", "telda"]),
        ("I will build a responsive landing page", "A fast, mobile-friendly page built around your product or portfolio.", "development", 2400, "Omar", ["vodafone_cash", "instapay"]),
        ("I will edit your short promotional video", "Clean cuts, captions and pacing, exported for social media.", "video", 700, "Youssef", ["fawry", "instapay"]),
        ("I will write clear Arabic or English website copy", "Natural copy for your homepage, services or product.", "writing", 500, "Nour", ["telda", "bank_transfer"]),
        ("I will create social media designs", "A consistent set of posts that gives your brand a recognizable look.", "marketing", 950, "Salma", ["orange_cash", "instapay"]),
        ("I will create a simple business website", "A small business site with clear sections and a mobile layout.", "development", 3200, "Ahmed", ["bank_transfer", "instapay"]),
    ]
    for t, desc, cat, price, seller, pays in demos:
        cur = d.execute("INSERT INTO gigs(user_id,title,description,category,price,seller_name,status,is_demo) VALUES(NULL,?,?,?,?,?,'approved',1)",
                        (t, desc, cat, price, seller))
        d.executemany("INSERT INTO gig_payments VALUES(?,?)", [(cur.lastrowid, p) for p in pays])
    d.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
