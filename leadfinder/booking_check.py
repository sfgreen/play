"""Check clinic websites for online booking.

Usage: python booking_check.py clean.csv out.csv
Adds a `booking` column: online / unclear / none / site_down.
Only checks strong leads (column `strong` = yes) that have a real website.
"""
import csv
import os
import re
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# Booking and scheduling tools used by clinics, spas and massage therapists.
VENDORS = [
    "janeapp.com", "vagaro.com", "mindbodyonline.com", "mindbody.io", "clients.mindbodyonline",
    "squareup.com/appointments", "square.site", "book.squareup", "acuityscheduling.com",
    "as.me", "calendly.com", "schedulicity.com", "genbook.com", "fresha.com", "joinblvd.com",
    "boulevard.io", "zenoti.com", "glossgenius.com", "intakeq.com", "simplepractice.com",
    "setmore.com", "booksy.com", "noterro.com", "massagebook.com", "clinicsense.com",
    "zocdoc.com", "nexhealth.com", "localmed.com", "solutionreach.com", "weave",
    "chirotouch", "chirofusion", "practicebetter.io", "practicepanther", "unifiedpractice.com",
    "acubliss.com", "mangomint.com", "phorest.com", "aestheticspro.com", "patientnow.com",
    "myaestheticspro", "rosyapp.com", "booker.com", "styleseat.com", "schedulista.com",
    "appointy.com", "simplybook", "10to8.com", "youcanbook.me", "tebra.com", "kareo.com",
    "webpt.com", "prompt health", "promptemr", "hellohero", "healthie.com", "practiceq",
    "spaasoft", "schedulicity", "wellnessliving.com", "gettimely.com", "jane.app",
    "squarespacescheduling", "wixbookings", "bookings-widget", "chirohd", "genesischiro", "zenplanner",
]
BOOK_TEXT = re.compile(r"book (now|online|an? appointment|your|today)|schedule (now|online|an? appointment|your)|"
                       r"request an? appointment|online booking|make an appointment", re.I)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


# Send plain-http requests through the same proxy as https ones.
_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": _proxy, "https": _proxy} if _proxy else {}))


def fetch(url):
    # Try https first; many listings still link the old http address.
    tries = [url.replace("http://", "https://", 1), url] if url.startswith("http://") else [url]
    last = None
    for u in tries:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "text/html"})
            with _opener.open(req, timeout=15) as r:
                return r.read(600_000).decode("utf-8", "ignore")
        except Exception as e:
            last = e
    raise last


def check(row):
    url = row["website"]
    try:
        html = fetch(url)
    except Exception as e:
        row["booking"], row["booking_detail"] = "site_down", type(e).__name__
        return row
    low = html.lower()
    vendor = next((v for v in VENDORS if v in low), None)
    if vendor:
        row["booking"], row["booking_detail"] = "online", vendor
    elif BOOK_TEXT.search(html):
        row["booking"], row["booking_detail"] = "unclear", BOOK_TEXT.search(html).group(0)
    else:
        row["booking"], row["booking_detail"] = "none", ""
    return row


def main(src, out):
    rows = [r for r in csv.DictReader(open(src)) if r["strong"] and r["has_real_site"] == "yes"]
    # A domain shared by several listings means a multi-location group, not an independent clinic.
    domains = Counter(urlparse(r["website"]).netloc.replace("www.", "") for r in rows)
    rows = [r for r in rows if domains[urlparse(r["website"]).netloc.replace("www.", "")] < 2
            and "/locations/" not in r["website"] and "/location/" not in r["website"]]
    print(f"checking {len(rows)} independent clinic websites...", file=sys.stderr)
    with ThreadPoolExecutor(24) as pool:
        done = list(pool.map(check, rows))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(done[0].keys()))
        w.writeheader()
        w.writerows(done)
    c = Counter(r["booking"] for r in done)
    print(dict(c), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
