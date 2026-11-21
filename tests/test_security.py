import io, os, re, shutil, tempfile, unittest
from egy import create_app
from egy import security as sec

PW = "Corr3ct-horse-battery"
IBAN_OK = "Mariam Hassan | EG380019000500000000263180002"

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DB_PATH": f"{self.tmp}/t.db", "UPLOAD_DIR": f"{self.tmp}/up", "TESTING": True})
        self.app.config["TESTING_NO_LIMIT"] = True
    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)
    def client(self): return self.app.test_client()
    def token(self, c, url="/login"):
        return re.search(r'name="csrf_token" value="([^"]+)"', c.get(url).get_data(as_text=True)).group(1)
    def post(self, c, url, data=None, page="/login", **kw):
        data = dict(data or {}); data["csrf_token"] = self.token(c, page); return c.post(url, data=data, **kw)
    def register(self, email, role, name="Test User"):
        c = self.client()
        r = self.post(c, "/register", dict(display_name=name, email=email, password=PW, password2=PW, role=role, terms="on"), page="/register")
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300]); return c
    def freelancer_with_gig(self):
        f = self.register("free@example.com", "freelancer", "Mariam")
        self.post(f, "/account/payout", dict(method="instapay", details="mariam@instapay"), page="/account/profile")
        self.post(f, "/account/portfolio", dict(title="Brand work", link_url="https://example.com/x"), page="/account/profile")
        r = self.post(f, "/freelancer/post-gig", dict(title="I will design your logo today", description="x" * 40, category="design", price="500", payments="instapay"), page="/freelancer/post-gig")
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            from egy.db import get_db; d = get_db(); d.execute("UPDATE gigs SET status='approved' WHERE user_id IS NOT NULL"); d.commit()
            gid = d.execute("SELECT id FROM gigs WHERE user_id IS NOT NULL").fetchone()[0]
        return f, gid

class TestHeadersAndCsrf(Base):
    def test_headers(self):
        h = self.client().get("/").headers
        for k in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"): self.assertIn(k, h)
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"]); self.assertNotIn("unsafe-inline", h["Content-Security-Policy"])
    def test_no_inline_script_or_style_in_pages(self):
        c = self.client()
        for u in ("/", "/explore", "/why-us", "/login", "/register", "/gig/1"):
            html = c.get(u).get_data(as_text=True)
            self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)[^>]*>"); self.assertNotRegex(html, r'\sstyle="'); self.assertNotRegex(html, r"\son\w+=")
    def test_csrf_required(self):
        c = self.client(); c.get("/login")
        self.assertEqual(c.post("/login", data=dict(email="a@b.co", password="x")).status_code, 403)
        self.assertEqual(c.post("/logout").status_code, 403)
    def test_cross_origin_rejected(self):
        c = self.client(); t = self.token(c)
        self.assertEqual(c.post("/login", data=dict(email="a@b.co", password="x", csrf_token=t), headers={"Origin": "https://evil.example"}).status_code, 403)
    def test_cookie_flags(self):
        c = self.client(); ck = c.get("/login").headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", ck); self.assertIn("SameSite=Lax", ck)

class TestAuth(Base):
    def test_register_login_logout(self):
        c = self.register("a@example.com", "client")
        self.assertEqual(c.get("/account").status_code, 200)
        self.post(c, "/logout", page="/account"); self.assertEqual(c.get("/account").status_code, 302)
        r = self.post(c, "/login", dict(email="A@Example.com", password=PW)); self.assertEqual(r.status_code, 302)
    def test_weak_password_rejected(self):
        c = self.client()
        r = self.post(c, "/register", dict(display_name="X Y", email="w@example.com", password="password", password2="password", role="client", terms="on"), page="/register")
        self.assertEqual(r.status_code, 400)
    def test_no_user_enumeration(self):
        self.register("known@example.com", "client"); c = self.client()
        a = self.post(c, "/login", dict(email="known@example.com", password="Wrong-pass-123")); b = self.post(c, "/login", dict(email="nobody@example.com", password="Wrong-pass-123"))
        self.assertEqual(a.status_code, b.status_code); self.assertEqual(re.findall(r'role="alert">([^<]+)', a.get_data(as_text=True)), re.findall(r'role="alert">([^<]+)', b.get_data(as_text=True)))
        dup = self.post(self.client(), "/register", dict(display_name="D D", email="known@example.com", password=PW, password2=PW, role="client", terms="on"), page="/register")
        self.assertNotIn("already exists", dup.get_data(as_text=True))
    def test_lockout(self):
        self.register("lock@example.com", "client"); c = self.client()
        for _ in range(5): self.post(c, "/login", dict(email="lock@example.com", password="bad-Pass-1234"))
        r = self.post(c, "/login", dict(email="lock@example.com", password=PW)); self.assertEqual(r.status_code, 429)
    def test_open_redirect_blocked(self):
        self.register("o@example.com", "client"); c = self.client()
        for bad in ("https://evil.example", "//evil.example", "/\\evil.example"):
            r = self.post(c, "/login?next=" + bad, dict(email="o@example.com", password=PW, next=bad)); self.assertNotIn("evil", r.headers.get("Location", ""))
    def test_session_fixation_rotates_csrf(self):
        self.register("s@example.com", "client"); c = self.client(); before = self.token(c); self.post(c, "/login", dict(email="s@example.com", password=PW)); self.assertNotEqual(before, self.token(c, "/account"))

class TestDataProtection(Base):
    def test_pii_not_in_database_file(self):
        f, gid = self.freelancer_with_gig()
        raw = open(f"{self.tmp}/t.db", "rb").read() + (open(f"{self.tmp}/t.db-wal", "rb").read() if os.path.exists(f"{self.tmp}/t.db-wal") else b"")
        for secret in (b"free@example.com", b"mariam@instapay", PW.encode()): self.assertNotIn(secret, raw)
    def test_message_encrypted_and_aad_bound(self):
        f, gid = self.freelancer_with_gig(); c = self.register("cl@example.com", "client")
        r = self.post(c, f"/gig/{gid}/order", dict(payment_method="instapay", message="my secret brief 12345"), page=f"/gig/{gid}"); self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            from egy.db import get_db; row = get_db().execute("SELECT body_enc FROM messages").fetchone()
            self.assertNotIn(b"secret brief", bytes(row[0]))
            with self.assertRaises(Exception): sec.decrypt(row[0], "msg.999")
    def test_password_hash_format(self):
        self.register("h@example.com", "client")
        with self.app.app_context():
            from egy.db import get_db; h = get_db().execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertTrue(h.startswith("scrypt$")); self.assertNotIn(PW, h)

class TestOrdersAndAccess(Base):
    def flow(self):
        f, gid = self.freelancer_with_gig(); c = self.register("cl@example.com", "client")
        self.post(c, f"/gig/{gid}/order", dict(payment_method="instapay", message="Please make a logo"), page=f"/gig/{gid}")
        return f, c, gid
    def test_payout_hidden_until_accepted_and_only_to_client(self):
        f, c, gid = self.flow()
        self.assertNotIn("mariam@instapay", c.get("/orders/1").get_data(as_text=True))
        self.post(f, "/orders/1/status", dict(status="accepted"), page="/orders/1")
        self.assertIn("mariam@instapay", c.get("/orders/1").get_data(as_text=True))
        self.post(c, "/orders/1/status", dict(status="paid_by_client", reference="REF1"), page="/orders/1")
        self.assertNotIn("mariam@instapay", c.get("/orders/1").get_data(as_text=True))
    def test_idor_other_users_cannot_see_order(self):
        f, c, gid = self.flow(); x = self.register("x@example.com", "client")
        self.assertEqual(x.get("/orders/1").status_code, 404)
        self.assertEqual(self.post(x, "/orders/1/message", dict(body="hi"), page="/account").status_code, 404)
    def test_illegal_transitions_blocked(self):
        f, c, gid = self.flow()
        self.assertEqual(self.post(c, "/orders/1/status", dict(status="completed"), page="/orders/1").status_code, 403)
        self.assertEqual(self.post(c, "/orders/1/status", dict(status="accepted"), page="/orders/1").status_code, 403)
        self.assertEqual(self.post(f, "/orders/1/status", dict(status="payment_confirmed"), page="/orders/1").status_code, 403)
    def test_full_happy_path(self):
        f, c, gid = self.flow()
        for who, st in ((f, "accepted"), (c, "paid_by_client"), (f, "payment_confirmed"), (f, "delivered"), (c, "completed")):
            self.assertEqual(self.post(who, "/orders/1/status", dict(status=st), page="/orders/1").status_code, 302, st)
    def test_role_enforcement(self):
        f, gid = self.freelancer_with_gig(); c = self.register("c@example.com", "client")
        self.assertEqual(c.get("/freelancer/post-gig").status_code, 403)
        self.assertEqual(f.get("/post-project").status_code, 403)
    def test_cannot_order_own_or_unapproved_gig(self):
        f, gid = self.freelancer_with_gig(); self.assertEqual(self.post(f, f"/gig/{gid}/order", dict(payment_method="instapay", message="hello there"), page="/account").status_code, 403)
    def test_gig_requires_portfolio_and_payout(self):
        f = self.register("n@example.com", "freelancer")
        r = self.post(f, "/freelancer/post-gig", dict(title="I will design your logo", description="x" * 40, category="design", price="5", payments="instapay"), page="/freelancer/post-gig"); self.assertEqual(r.status_code, 400)

class TestInjection(Base):
    def test_sql_injection_search(self):
        c = self.client()
        for p in ("' OR 1=1 --", "%", "_", "\"; DROP TABLE gigs;--"):
            r = c.get("/api/gigs", query_string={"search": p}); self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get("/api/gigs").get_json()["gigs"].__len__(), 6)
        self.assertEqual(len(c.get("/api/gigs", query_string={"search": "%"}).get_json()["gigs"]), 0)
        self.assertEqual(c.get("/api/gigs?category=x' OR '1").status_code, 400)
    def test_xss_escaped(self):
        f, gid = self.freelancer_with_gig(); c = self.register("cl@example.com", "client")
        self.post(c, f"/gig/{gid}/order", dict(payment_method="instapay", message="<script>alert(1)</script>"), page=f"/gig/{gid}")
        html = c.get("/orders/1").get_data(as_text=True); self.assertNotIn("<script>alert", html); self.assertIn("&lt;script&gt;", html)
    def test_javascript_url_rejected_in_portfolio(self):
        f = self.register("p@example.com", "freelancer")
        self.post(f, "/account/portfolio", dict(title="Bad link", link_url="javascript:alert(1)"), page="/account/profile")
        with self.app.app_context():
            from egy.db import get_db; self.assertEqual(get_db().execute("SELECT COUNT(*) FROM portfolio_items").fetchone()[0], 0)

class TestUploadsAndAdmin(Base):
    def test_non_image_rejected_and_real_image_reencoded(self):
        from PIL import Image
        f = self.register("u@example.com", "freelancer"); t = self.token(f, "/account/profile")
        bad = f.post("/account/portfolio", data=dict(csrf_token=t, title="Evil", image=(io.BytesIO(b"<?php system($_GET[0]); ?>"), "x.jpg")), content_type="multipart/form-data")
        buf = io.BytesIO(); Image.new("RGB", (50, 50), "red").save(buf, "PNG"); buf.seek(0)
        f.post("/account/portfolio", data=dict(csrf_token=t, title="Good", image=(buf, "../../evil.php")), content_type="multipart/form-data")
        files = os.listdir(f"{self.tmp}/up"); self.assertEqual(len(files), 1); self.assertRegex(files[0], r"^[0-9a-f]{32}\.webp$")
        self.assertEqual(f.get("/media/" + files[0]).status_code, 200); self.assertEqual(f.get("/media/..%2f..%2fetc%2fpasswd").status_code, 404)
    def test_admin_hidden_from_normal_users(self):
        c = self.register("c@example.com", "client"); self.assertEqual(c.get("/admin/").status_code, 404)
        self.assertEqual(self.client().get("/admin/").status_code, 302)
    def test_cannot_self_register_as_admin(self):
        c = self.client(); r = self.post(c, "/register", dict(display_name="Ad Min", email="adm@example.com", password=PW, password2=PW, role="admin", terms="on"), page="/register"); self.assertEqual(r.status_code, 400)
    def test_delete_account_wipes_data(self):
        f, gid = self.freelancer_with_gig(); self.post(f, "/account/delete", dict(password=PW), page="/account/profile")
        with self.app.app_context():
            from egy.db import get_db; d = get_db()
            self.assertEqual(d.execute("SELECT COUNT(*) FROM payout_methods").fetchone()[0], 0)
            self.assertEqual(d.execute("SELECT is_active FROM users").fetchone()[0], 0)

class TestRateLimit(Base):
    def test_login_rate_limited(self):
        self.app.config["TESTING_NO_LIMIT"] = False; c = self.client(); codes = set()
        for _ in range(25): codes.add(self.post(c, "/login", dict(email="z@example.com", password="x")).status_code)
        self.assertIn(429, codes)

if __name__ == "__main__": unittest.main()
