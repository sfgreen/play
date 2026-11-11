"""Combine the region scan and booking check into one ranked lead list."""
import csv, re, sys
from collections import Counter

BIG = re.compile(r"urgent care|home health|hospital|dermatology|clinica|afc |woodhouse|ignite medical|"
                 r"emergency|pediatric|family medicine|primary care|imaging|radiology", re.I)

clean = list(csv.DictReader(open("georgetown_wellness_clean.csv")))
checked = {r["maps_url"]: r for r in csv.DictReader(open("georgetown_booking.csv"))}
out = []
for r in clean:
    if not r["strong"] or BIG.search(r["name"]):
        continue
    if r["has_real_site"] == "no":
        r["tier"], r["pitch"] = "1", "No website: site + online booking"
        r["booking"] = r["booking_detail"] = ""
    else:
        c = checked.get(r["maps_url"])
        if not c or c["booking"] != "none" or int(r["reviews"]) > 300 or "book" in r["website"].lower():
            continue
        r["tier"], r["pitch"] = "2", "Has a site, no online booking found: booking add-on or new site"
        r["booking"], r["booking_detail"] = c["booking"], c["booking_detail"]
    r["status"] = r["notes"] = ""
    out.append(r)

out.sort(key=lambda r: (r["tier"], -int(r["reviews"])))
cols = ["tier", "pitch", "name", "category", "rating", "reviews", "phone", "address", "miles",
        "website", "maps_url", "status", "notes"]
with open(sys.argv[1], "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(out)
print(Counter(r["tier"] for r in out))
print(Counter((r["tier"], r["search"]) for r in out).most_common())
for r in [x for x in out if x["tier"] == "2"][:12]:
    print(f'{r["name"][:36]:36} | {r["category"][:14]:14} | {r["rating"]} ({r["reviews"]}) | {r["address"].split(",")[-3].strip():12} | {r["website"][:38]}')
