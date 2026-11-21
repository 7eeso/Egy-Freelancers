import re, unicodedata
from urllib.parse import urlparse

class Invalid(ValueError):
    pass

def text(value, label, min_len=1, max_len=200, multiline=False):
    v = unicodedata.normalize("NFKC", str(value or "")).strip()
    v = "".join(c for c in v if c in "\n\t" and multiline or (unicodedata.category(c)[0] != "C"))
    if len(v) < min_len: raise Invalid(f"{label} is required." if min_len == 1 else f"{label} must be at least {min_len} characters.")
    if len(v) > max_len: raise Invalid(f"{label} is too long (max {max_len}).")
    return v

def integer(value, label, lo, hi):
    try: n = int(str(value).strip())
    except (TypeError, ValueError): raise Invalid(f"{label} must be a number.")
    if not lo <= n <= hi: raise Invalid(f"{label} must be between {lo:,} and {hi:,}.")
    return n

def choice(value, label, allowed):
    if value not in allowed: raise Invalid(f"Choose a valid {label}.")
    return value

def url(value, label):
    v = str(value or "").strip()
    if not v: return ""
    if len(v) > 300: raise Invalid(f"{label} is too long.")
    p = urlparse(v)
    if p.scheme not in ("http", "https") or not p.netloc or any(c in v for c in " <>\"'\\"):
        raise Invalid(f"{label} must be a valid http(s) link.")
    return v

def iban_ok(s):
    s = s.replace(" ", "").upper()
    if not re.fullmatch(r"EG\d{27}", s): return False
    n = int("".join(str(int(c, 36)) for c in s[4:] + s[:4]))
    return n % 97 == 1

def payout(method, value):
    v = text(value, "Payment details", 3, 120)
    if method in ("vodafone_cash", "orange_cash", "etisalat_cash"):
        if not re.fullmatch(r"01[0125]\d{8}", v.replace(" ", "")): raise Invalid("Enter a valid Egyptian mobile wallet number (e.g. 01012345678).")
        return v.replace(" ", "")
    if method == "bank_transfer":
        m = re.fullmatch(r"(.{3,60})\s*[|,]\s*(EG[\d ]{27,40})", v, re.I)
        if not m or not iban_ok(m.group(2)): raise Invalid("Use the format: Account holder name | EG IBAN (29 characters).")
        return f"{m.group(1).strip()} | {m.group(2).replace(' ', '').upper()}"
    if method == "wise_payoneer" and "@" not in v: raise Invalid("Enter the email linked to your Wise/Payoneer account.")
    return v
