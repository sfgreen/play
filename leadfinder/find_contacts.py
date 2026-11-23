"""Find public contact emails and social links on lead websites.

Usage: python find_contacts.py leads.csv out.csv
Checks the homepage plus a contact/about page if one is linked.
"""
import csv
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": _proxy, "https": _proxy} if _proxy else {}))
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
JUNK = re.compile(r"\.(png|jpg|jpeg|gif|webp|svg)$|example\.|sentry|wixpress|godaddy|domain\.com|yourdomain|"
                  r"@sentry|squarespace|wordpress|schema\.org", re.I)
SOCIAL = {"facebook": re.compile(r"https?://(?:www\.)?facebook\.com/[^\"'\s<>?]+", re.I),
          "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[^\"'\s<>?]+", re.I)}
CONTACT_LINK = re.compile(r'href=["\']([^"\']*(?:contact|about)[^"\']*)["\']', re.I)


def get(url):
    tries = [url.replace("http://", "https://", 1), url] if url.startswith("http://") else [url]
    for u in tries:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with _opener.open(req, timeout=15) as r:
                return r.read(600_000).decode("utf-8", "ignore")
        except Exception:
            pass
    return ""


def scan(row):
    site = row.get("website", "")
    pages = []
    if site and "facebook.com" not in site and "instagram.com" not in site:
        home = get(site)
        pages.append(home)
        m = CONTACT_LINK.search(home)
        if m:
            pages.append(get(urljoin(site, m.group(1))))
    text = " ".join(pages)
    emails = sorted({e.lower() for e in EMAIL.findall(text) if not JUNK.search(e)})
    row["email"] = ", ".join(emails[:3])
    for k, rx in SOCIAL.items():
        found = [u for u in rx.findall(text) if "sharer" not in u and "/tr" not in u]
        row[k] = found[0] if found else ""
    if "facebook.com" in site:
        row["facebook"] = site
    if "instagram.com" in site:
        row["instagram"] = site
    return row


rows = list(csv.DictReader(open(sys.argv[1])))
with ThreadPoolExecutor(20) as pool:
    rows = list(pool.map(scan, rows))
cols = list(rows[0].keys())
with open(sys.argv[2], "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
for t in ("1", "2"):
    sub = [r for r in rows if r["tier"] == t]
    print(f"Tier {t}: {len(sub)} leads | phone {sum(bool(r['phone']) for r in sub)} | email {sum(bool(r['email']) for r in sub)} "
          f"| facebook {sum(bool(r['facebook']) for r in sub)} | instagram {sum(bool(r['instagram']) for r in sub)}")
