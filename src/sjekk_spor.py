"""
Diagnose: hva inneholder trackAnalysis egentlig?

Kjor:
    python src/sjekk_spor.py

Leser de cachede sporfilene og teller hvor ofte hvert analysefelt er utfylt.
Ingen API-kall.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROT = Path(__file__).resolve().parents[1]
CACHE = ROT / "data" / "raw" / "spor"
PUNKTER = ROT / "data" / "raw" / "spor_punkter"

LISTEFELT = [
    "slaughterhouseVisits",
    "localityWaypoints",
    "diseaseZoneVisits",
    "productionAreaVisits",
]

FLAGGFELT = [
    "hasSlaughterhouseVisitsAnalysis",
    "hasDiseaseZoneVisitsAnalysis",
    "hasProductionAreaVisitsAnalysis",
]


def main():
    filer = sorted(CACHE.glob("*.json"))
    if not filer:
        raise SystemExit("Ingen cachede sporfiler. Kjor hent_spor.py forst.")

    print(f"Leser {len(filer)} cachede sporfiler\n")

    flagg = {f: Counter() for f in FLAGGFELT}
    lengder = {f: Counter() for f in LISTEFELT}
    mangler_analyse = 0
    ingen_punkter = 0
    eksempel = None
    alle_nokler = Counter()

    for fil in filer:
        try:
            data = json.loads(fil.read_text(encoding="utf-8"))
        except Exception:
            continue

        if data.get("n_punkter", 1) == 0:
            ingen_punkter += 1

        analyse = data.get("trackAnalysis")
        if not isinstance(analyse, dict):
            mangler_analyse += 1
            continue

        alle_nokler.update(analyse.keys())

        for f in FLAGGFELT:
            flagg[f][analyse.get(f)] += 1

        for f in LISTEFELT:
            verdi = analyse.get(f)
            n = len(verdi) if isinstance(verdi, list) else -1
            lengder[f][n] += 1

            if n > 0 and eksempel is None and f == "localityWaypoints":
                eksempel = (fil.name, f, verdi[0])

    print(f"Filer uten trackAnalysis : {mangler_analyse}")
    print(f"Filer uten posisjoner    : {ingen_punkter}  (fartoyet var ikke i drift)")

    print(f"\nAlle felter i trackAnalysis:")
    for nokkel, antall in alle_nokler.most_common():
        print(f"  {nokkel:38s} {antall}")

    print(f"\n--- ANALYSEFLAGG ---")
    for f in FLAGGFELT:
        if flagg[f]:
            fordeling = ", ".join(f"{k}: {v}" for k, v in flagg[f].most_common())
            print(f"  {f:36s} {fordeling}")

    print(f"\n--- LISTELENGDER (antall filer per lengde) ---")
    for f in LISTEFELT:
        c = lengder[f]
        if not c:
            continue
        tomme = c.get(0, 0)
        mangler = c.get(-1, 0)
        utfylt = sum(v for k, v in c.items() if k > 0)
        print(f"  {f:26s} utfylt: {utfylt:5d}   tom: {tomme:5d}   mangler: {mangler:5d}")

    if eksempel:
        fil, felt, verdi = eksempel
        print(f"\n--- EKSEMPEL: {felt} fra {fil} ---")
        if isinstance(verdi, dict):
            for k, v in verdi.items():
                print(f"  {k:28s} {str(v)[:48]}")
        else:
            print(f"  {str(verdi)[:200]}")

    punktfiler = sorted(PUNKTER.glob("*.json")) if PUNKTER.exists() else []
    print(f"\n--- FULLE SPOR LAGRET ---")
    if punktfiler:
        for f in punktfiler:
            mb = f.stat().st_size / 1e6
            print(f"  {f.name}  ({mb:.1f} MB)")
    else:
        print("  Ingen. Reservelosningen krever disse - se melding under.")


if __name__ == "__main__":
    main()
