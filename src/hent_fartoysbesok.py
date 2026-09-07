"""

"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.barentswatch import BarentsWatchKlient

ROT = Path(__file__).resolve().parents[1]
CACHE = ROT / "data" / "raw" / "fartoysbesok"

AAR = 2025
PAUSE_SEK = 0.5


def hent_lokalitet(bw: BarentsWatchKlient, lokalitet_no: int, aar: int):
    """Hent alle fartoysbesok for en lokalitet i et ar, med disk-cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fil = CACHE / f"{lokalitet_no}-{aar}.json"

    if fil.exists():
        return json.loads(fil.read_text(encoding="utf-8"))

    data = bw.get(f"/bwapi/v1/geodata/fishhealth/locality/{lokalitet_no}/vessel/{aar}")

    fil.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(PAUSE_SEK)
    return data


def flat_ut(data, lokalitet_no: int) -> list[dict]:
    """
    Gjor svaret om til en liste med flate rader.

    Vi vet ikke sikkert hvordan API-et strukturerer svaret, sa denne
    handterer bade en ren liste og et objekt med lista under en nokkel.
    """
    if isinstance(data, dict):
        for nokkel in ("vessels", "vesselVisits", "visits", "data", "items"):
            if nokkel in data and isinstance(data[nokkel], list):
                data = data[nokkel]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        return []

    rader = []
    for element in data:
        if isinstance(element, dict):
            rad = dict(element)
            rad["localityNo"] = lokalitet_no
            rader.append(rad)
    return rader


def main():
    lok_fil = ROT / "data" / "processed" / "lokaliteter.csv"
    if not lok_fil.exists():
        print("Fant ikke lokaliteter.csv. Kjor hent_lokaliteter.py forst.")
        return

    lokaliteter = pd.read_csv(lok_fil)
    print(f"Henter fartoysbesok for {len(lokaliteter)} lokaliteter, ar {AAR}\n")

    bw = BarentsWatchKlient()
    alle = []
    feil = 0

    for i, rad in lokaliteter.iterrows():
        lok_no = int(rad["lokalitet_id"])
        try:
            data = hent_lokalitet(bw, lok_no, AAR)
        except Exception as e:
            print(f"  {lok_no}: FEIL - {e}")
            feil += 1
            continue

        rader = flat_ut(data, lok_no)
        alle.extend(rader)
        print(f"  [{i + 1:3d}/{len(lokaliteter)}] lokalitet {lok_no}: {len(rader)} rader")

    if not alle:
        print("\nIngen data returnert. Sjekk et enkeltkall i Swagger.")
        return

    df = pd.json_normalize(alle)

    mappe = ROT / "data" / "processed"
    df.to_csv(mappe / "fartoysbesok_raa.csv", index=False)

    print(f"\n{'=' * 60}")
    print(f"{len(df)} rader totalt, {feil} feilede lokaliteter")
    print(f"Skrevet til data/processed/fartoysbesok_raa.csv")

    print(f"\nKOLONNER API-ET RETURNERER:")
    for kol in df.columns:
        eksempel = df[kol].dropna()
        vis = eksempel.iloc[0] if len(eksempel) else "(alle tomme)"
        print(f"  {kol:35s} eks: {str(vis)[:45]}")

    print(f"\nFORSTE 3 RADER:")
    print(df.head(3).to_string())


if __name__ == "__main__":
    main()
