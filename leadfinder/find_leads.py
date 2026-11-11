"""Find local businesses on Google Maps with no real website.

Usage: python find_leads.py "Ocala, FL" out.csv
The Places API key is added by the environment's network proxy, so none is set here.
"""
import csv
import json
import sys
import time
import urllib.request

CATEGORIES = [
    "plumber", "roofer", "HVAC contractor", "electrician", "landscaper",
    "lawn care", "pool service", "house cleaning", "handyman", "pressure washing",
    "painter", "auto repair", "hair salon", "barber shop", "nail salon",
    "pest control", "tree service", "fence contractor", "flooring contractor",
    "mobile mechanic",
]

# A social page or booking link isn't a real website, so those count as leads too.
NOT_A_WEBSITE = ("facebook.com", "instagram.com", "yelp.com", "nextdoor.com",
                 "business.site", "linktr.ee", "square.site", "tiktok.com")

FIELDS = ",".join("places." + f for f in [
    "id", "displayName", "formattedAddress", "nationalPhoneNumber", "websiteUri",
    "rating", "userRatingCount", "primaryTypeDisplayName", "googleMapsUri",
    "businessStatus",
]) + ",nextPageToken"


def search(query, page_token=None):
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


def main(city, out_path):
    state = city.split(",")[-1].strip()
    seen, rows = set(), []
    for cat in CATEGORIES:
        token = None
        for _ in range(3):  # the API returns at most 60 results per query
            data = search(f"{cat} in {city}", token)
            for p in data.get("places", []):
                if p["id"] in seen or p.get("businessStatus") != "OPERATIONAL":
                    continue
                if f", {state} " not in p.get("formattedAddress", ""):
                    continue
                seen.add(p["id"])
                site = p.get("websiteUri", "")
                if site and not any(s in site for s in NOT_A_WEBSITE):
                    continue
                rows.append({
                    "name": p["displayName"]["text"],
                    "category": p.get("primaryTypeDisplayName", {}).get("text", cat),
                    "search": cat,
                    "rating": p.get("rating", ""),
                    "reviews": p.get("userRatingCount", 0),
                    "phone": p.get("nationalPhoneNumber", ""),
                    "address": p.get("formattedAddress", ""),
                    "current_link": site,
                    "maps_url": p.get("googleMapsUri", ""),
                })
            token = data.get("nextPageToken")
            if not token:
                break
            time.sleep(1)
        print(f"{cat}: {len(seen)} businesses checked, {len(rows)} leads so far", file=sys.stderr)

    rows.sort(key=lambda r: (-(r["reviews"] or 0)))
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["name"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(seen)} businesses checked, {len(rows)} without a real website -> {out_path}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
