"""Build a compact Indian gazetteer from the GeoNames IN dump.

Why this exists: the prototype shipped a hand-written 65-city table, which was
fine for synthetic traffic that only ever named those 65 cities. Real news
headlines do not cooperate — measured on live Google News articles, **0 of 6
geocoded**, because they name states and districts ("Uttarakhand", "Bihar and
UP districts", "Uttarkashi") rather than metros.

Source: https://download.geonames.org/export/dump/IN.zip
Licence: CC BY 4.0 — attribution to GeoNames is required wherever this data is
used or redistributed. Recorded in README.

Run once:
    python build_gazetteer.py --dump /path/to/IN.txt \
        --admin1 /path/to/admin1CodesASCII.txt \
        --admin2 /path/to/admin2Codes.txt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

OUT = Path("data/gazetteer.json")

# A town small enough to be below this is also small enough that a bare name
# match is more likely to be a false positive than a real location. States and
# districts come in regardless of population, since they are the unit an IMD
# bulletin actually speaks in.
MIN_POPULATION = 5000
ADMIN_CODES = {"ADM1", "ADM2"}


# Place names that are also ordinary English words. Blanket-excluding them is
# wrong — it would delete Agra, Assam, Amritsar and Darjeeling — so they are
# marked instead, and the resolver requires them to appear capitalised. The
# English word "than" is lowercase mid-sentence; the Gujarat town Than is not.
# This was a real false positive: "Floods kill more than 100 in Thailand and
# India" resolved to Than, Gujarat.
FALLBACK_COMMON = {
    "along", "bank", "bare", "begun", "mango", "manor", "moth", "punch",
    "rail", "salon", "samba", "than", "tundra", "wail", "weir", "canning",
    "karma", "pail", "manor", "bali", "bora", "kari", "karo", "maro", "mora",
}


def english_words() -> set[str]:
    """The system word list when present, a small builtin otherwise. Only used
    to *mark* names as ambiguous, never to drop them."""
    from pathlib import Path as _P

    for candidate in ("/usr/share/dict/words", "/usr/dict/words"):
        path = _P(candidate)
        if path.exists():
            try:
                return {
                    w.strip().lower()
                    for w in path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if w.strip()
                }
            except Exception:
                break
    return set(FALLBACK_COMMON)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--admin1", required=True)
    ap.add_argument("--admin2", required=True)
    args = ap.parse_args()

    # admin1: "IN.36" -> "Uttarakhand"
    states: dict[str, str] = {}
    for line in Path(args.admin1).read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith("IN."):
            states[parts[0].split(".", 1)[1]] = parts[1]

    # admin2: "IN.36.123" -> "Uttarkashi"
    districts: dict[tuple[str, str], str] = {}
    for line in Path(args.admin2).read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith("IN."):
            bits = parts[0].split(".")
            if len(bits) == 3:
                districts[(bits[1], bits[2])] = parts[1]

    dictionary = english_words() or FALLBACK_COMMON
    entries: dict[str, dict] = {}
    kept = 0
    with open(args.dump, encoding="utf-8") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 15:
                continue
            name, ascii_name = f[1], f[2]
            lat, lon = f[4], f[5]
            fclass, fcode = f[6], f[7]
            adm1, adm2 = f[10], f[11]
            try:
                population = int(f[14] or 0)
            except ValueError:
                population = 0

            is_admin = fcode in ADMIN_CODES
            if not is_admin and (fclass != "P" or population < MIN_POPULATION):
                continue

            state = states.get(adm1)
            district = districts.get((adm1, adm2))
            record = {
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "state": state,
                "district": district or (name if fcode == "ADM2" else None),
                "population": population,
                "kind": "state" if fcode == "ADM1" else ("district" if fcode == "ADM2" else "town"),
            }

            variants = {name, ascii_name}
            if fcode == "ADM1":
                # GeoNames calls many Indian states "State of Rajasthan" or
                # "Union Territory of Puducherry". No headline writes that, so
                # register the bare administrative name as well — it comes
                # from admin1CodesASCII.txt already clean.
                if state:
                    variants.add(state)
                for prefix in (
                    "State of ",
                    "Union Territory of ",
                    "National Capital Territory of ",
                ):
                    for v in list(variants):
                        if v.startswith(prefix):
                            variants.add(v[len(prefix) :])

            for variant in variants:
                key = variant.strip().lower()
                if len(key) < 4:
                    # Two- and three-letter names collide with ordinary words
                    # ("Goa" is fine, "Pen" is not) more often than they help.
                    continue
                prev = entries.get(key)
                # A bigger place wins the name, and an administrative area
                # outranks a town of the same name: a headline saying "Bihar"
                # means the state, not a village called Bihar.
                if prev is None or (
                    (record["kind"] != "town", record["population"])
                    > (prev["kind"] != "town", prev["population"])
                ):
                    entries[key] = dict(
                        record, ambiguous=(" " not in key and key in dictionary)
                    )
            kept += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    by_kind: dict[str, int] = {}
    ambiguous = 0
    for r in entries.values():
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
        ambiguous += 1 if r.get("ambiguous") else 0
    print(f"kept {kept:,} places → {len(entries):,} searchable names")
    print(f"  by kind: {by_kind}")
    print(f"  {ambiguous} names are also English words (require capitalisation)")
    print(f"  written to {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
