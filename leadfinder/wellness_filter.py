"""Filter a region scan down to independent wellness clinics."""
import csv, re, sys
from collections import Counter

KEEP = {"chiropractor", "spa", "massage", "massage spa", "wellness center", "physical therapist",
        "skin care clinic", "med spa", "health"}
CLINIC_SEARCHES = {"med spa", "IV therapy", "acupuncture", "cryotherapy"}
PERSON = re.compile(r"(^Dr\.?\s)|\b(MD|M\.D\.|DO|DC|D\.C\.|DPT|PT|LMT|NP|APRN|FNP|PA-C|LAc|L\.Ac)\b")
CHAINS = re.compile(r"massage envy|hand ?& ?stone|elements massage|the joint|ati physical|restore hyper|"
                    r"drip ?bar|ideal image|laser ?away|european wax|athletico|upstream rehab|select physical|"
                    r"\bbswh?\b|baylor scott|ascension|st\.? david|texas physical therapy specialists|"
                    r"ivx|hydreight|massageluxe|zenoti|pt solutions|amped fitness|planet fitness", re.I)

rows = list(csv.DictReader(open(sys.argv[1])))
name_counts = Counter(re.sub(r"\W+", " ", r["name"].lower()).strip()[:18] for r in rows)
out = []
for r in rows:
    cat = r["category"].lower()
    if not (cat in KEEP or (cat in {"medical clinic", "doctor"} and r["search"] in CLINIC_SEARCHES)):
        continue
    if CHAINS.search(r["name"]) or name_counts[re.sub(r"\W+", " ", r["name"].lower()).strip()[:18]] >= 3:
        continue  # chains and franchises don't buy from local agencies
    if PERSON.search(r["name"]):
        continue  # a single provider's listing inside a bigger practice
    r["strong"] = "yes" if r["rating"] and float(r["rating"]) >= 4.5 and int(r["reviews"]) >= 25 else ""
    out.append(r)

with open(sys.argv[2], "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader(); w.writerows(out)

no_site = [r for r in out if r["has_real_site"] == "no"]
print("independent wellness clinics:", len(out))
print("  no real website:", len(no_site), "| strong:", sum(bool(r["strong"]) for r in no_site))
print("  have a website:", len(out) - len(no_site), "| strong:", sum(bool(r["strong"]) for r in out if r["has_real_site"] == "yes"))
print("\nno-site strong leads by type:", Counter(r["search"] for r in no_site if r["strong"]).most_common())
print()
for r in [r for r in no_site if r["strong"]][:20]:
    print(f'{r["name"][:38]:38} | {r["category"][:16]:16} | {r["rating"]} ({r["reviews"]}) | {r["address"].split(",")[-3].strip()} | {r["website"][:28]}')
