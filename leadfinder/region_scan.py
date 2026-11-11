"""Scan every town within a radius of a center point for one niche.

Usage: python region_scan.py out.csv
Keeps every operating business found (with or without a website) so a later
step can check which websites lack online booking.
"""
import csv
import json
import math
import sys
import time
import urllib.request

CENTER = (30.6327, -97.6772)  # Georgetown, TX
RADIUS_MI = 69
MAX_CALLS = 900  # hard cap on API calls to bound cost

CATEGORIES = [
    "chiropractor", "massage therapist", "med spa", "acupuncture",
    "IV therapy", "physical therapy", "wellness center", "cryotherapy",
]

# Towns inside the radius. Austin is split into areas because one search returns at most 60 results.
PLACES = [
    "North Austin, TX", "South Austin, TX", "East Austin, TX", "Downtown Austin, TX",
    "Northwest Austin, TX", "Southwest Austin, TX", "Central Austin, TX", "Southeast Austin, TX",
    "Round Rock, TX", "Georgetown, TX", "Cedar Park, TX", "Leander, TX", "Pflugerville, TX",
    "Hutto, TX", "Taylor, TX", "Liberty Hill, TX", "Jarrell, TX", "Manor, TX", "Elgin, TX",
    "Temple, TX", "Belton, TX", "Killeen, TX", "Harker Heights, TX", "Copperas Cove, TX",
    "Salado, TX", "Lampasas, TX", "Burnet, TX", "Marble Falls, TX", "Lago Vista, TX",
    "Lakeway, TX", "Bee Cave, TX", "Dripping Springs, TX", "Buda, TX", "Kyle, TX",
    "San Marcos, TX", "Wimberley, TX", "Lockhart, TX", "Bastrop, TX", "Smithville, TX",
    "Giddings, TX", "Rockdale, TX", "Cameron, TX",
]

NOT_A_WEBSITE = ("facebook.com", "instagram.com", "yelp.com", "nextdoor.com",
                 "business.site", "linktr.ee", "tiktok.com")

FIELDS = ",".join("places." + f for f in [
    "id", "displayName", "formattedAddress", "nationalPhoneNumber", "websiteUri",
    "rating", "userRatingCount", "primaryTypeDisplayName", "googleMapsUri",
    "businessStatus", "location",
]) + ",nextPageToken"

calls = 0


def miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def search(query, page_token=None):
    global calls
    calls += 1
    body = {"textQuery": query, "pageSize": 20}
    if page_token:
        body["pageToken"] = page_token
    req = urllib.request.Request(
        "https://places.googleapis.com/v1/places:searchText",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Goog-FieldMask": FIELDS},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main(out_path):
    found = {}
    for place in PLACES:
        for cat in CATEGORIES:
            token = None
            for _ in range(3):
                if calls >= MAX_CALLS:
                    break
                data = search(f"{cat} in {place}", token)
                for p in data.get("places", []):
                    loc = p.get("location")
                    if p.get("businessStatus") != "OPERATIONAL" or not loc:
                        continue
                    dist = miles(CENTER, (loc["latitude"], loc["longitude"]))
                    if dist > RADIUS_MI or p["id"] in found:
                        continue
                    site = p.get("websiteUri", "")
                    found[p["id"]] = {
                        "name": p["displayName"]["text"],
                        "category": p.get("primaryTypeDisplayName", {}).get("text", cat),
                        "search": cat,
                        "rating": p.get("rating", ""),
                        "reviews": p.get("userRatingCount", 0),
                        "phone": p.get("nationalPhoneNumber", ""),
                        "address": p.get("formattedAddress", ""),
                        "miles": round(dist, 1),
                        "website": site,
                        "has_real_site": "yes" if site and not any(s in site for s in NOT_A_WEBSITE) else "no",
                        "maps_url": p.get("googleMapsUri", ""),
                    }
                token = data.get("nextPageToken")
                if not token:
                    break
                time.sleep(1)
        no_site = sum(r["has_real_site"] == "no" for r in found.values())
        print(f"{place}: {len(found)} businesses, {no_site} without a site, {calls} API calls", file=sys.stderr)

    rows = sorted(found.values(), key=lambda r: -(r["reviews"] or 0))
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nDone: {len(rows)} businesses, {calls} API calls -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
