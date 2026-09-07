"""
Last ned lokalitetsregisteret fra BarentsWatch Fishhealth API.

Kjor:
    python src/hent_lokaliteter.py

Skriptet henter alle uker i valgt ar, cacher hvert svar til disk (slik at du
aldri henter samme uke to ganger), filtrerer geografisk, og skriver et samlet
lokalitetsregister til data/processed/lokaliteter.csv i det formatet
finn_besok() forventer.
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
CACHE = ROT / "data" / "raw" / "lokaliteter"

AAR = 2025
UKER = range(1, 53)

# Geografisk avgrensning. Standard: Nordmore og tilgrensende omrader.
# Utvid gjerne, men husk at storre omrade = mer data og lengre analyse.
BBOX = {
    "lat_min": 62.6,
    "lat_max": 64.2,
    "lon_min": 6.8,
    "lon_max": 9.5,
}

PAUSE_SEK = 0.5  # vaer hoflig mot en gratis offentlig tjeneste


def hent_uke(bw: BarentsWatchKlient, aar: int, uke: int) -> list[dict]:
    """Hent en uke, med disk-cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fil = CACHE / f"{aar}-{uke:02d}.json"

    if fil.exists():
        return json.loads(fil.read_text(encoding="utf-8"))

    data = bw.get(f"/bwapi/v1/geodata/fishhealth/localityradius/{aar}/{uke}")

    # API-et kan returnere enten en liste direkte eller et objekt med
    # lista under en nokkel. Handter begge.
    if isinstance(data, dict):
        for nokkel in ("localities", "data", "items"):
            if nokkel in data:
                data = data[nokkel]
                break

    fil.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(PAUSE_SEK)
    return data


def i_omraadet(rad: dict) -> bool:
    lat, lon = rad.get("lat"), rad.get("lon")
    if lat is None or lon is None:
        return False
    return (
        BBOX["lat_min"] <= lat <= BBOX["lat_max"]
        and BBOX["lon_min"] <= lon <= BBOX["lon_max"]
    )


def main():
    bw = BarentsWatchKlient()

    alle = []
    for uke in UKER:
        try:
            rader = hent_uke(bw, AAR, uke)
        except Exception as feil:
            print(f"  uke {uke:02d}: FEIL - {feil}")
            continue

        i_omr = [r for r in rader if i_omraadet(r)]
        for r in i_omr:
            r["_uke"] = uke
        alle.extend(i_omr)
        print(f"  uke {uke:02d}: {len(rader):5d} lokaliteter, {len(i_omr):4d} i omradet")

    if not alle:
        print("\nIngen lokaliteter funnet. Sjekk BBOX og at aret har data.")
        return

    df = pd.DataFrame(alle)

    # Ukesradene gjentar samme lokalitet. Vi vil ha ett register,
    # men beholder informasjon om hvor mange uker hver var aktiv.
    aktive_uker = df.groupby("localityNo")["_uke"].nunique().rename("aktive_uker")

    register = (
        df.sort_values("_uke")
        .groupby("localityNo", as_index=False)
        .last()
        .merge(aktive_uker, on="localityNo")
    )

    # Formatet finn_besok() forventer
    ut = pd.DataFrame(
        {
            "lokalitet_id": register["localityNo"],
            "navn": register["name"].fillna("").replace("", pd.NA),
            "lat": register["lat"],
            "lon": register["lon"],
            "aktive_uker": register["aktive_uker"],
        }
    )

    # Nyttige tilleggsfelt hvis de finnes
    for kilde, mal in [
        ("hasSalmonoids", "har_laksefisk"),
        ("isOnLand", "landbasert"),
        ("isSlaughterHoldingCage", "slaktemerd"),
        ("municipality", "kommune"),
    ]:
        if kilde in register.columns:
            ut[mal] = register[kilde]

    mappe = ROT / "data" / "processed"
    mappe.mkdir(parents=True, exist_ok=True)
    ut.to_csv(mappe / "lokaliteter.csv", index=False)

    print(f"\n{len(ut)} unike lokaliteter i omradet")
    print(f"Skrevet til data/processed/lokaliteter.csv")

    if ut["navn"].isna().all():
        print(
            "\nMERK: alle navn er tomme. Listeendepunktet gir ikke navn.\n"
            "Hent dem fra detaljendepunktet per lokalitet hvis du trenger dem:\n"
            "  /v1/geodata/fishhealth/locality/{localityNo}/{year}/{week}"
        )

    print("\nForste rader:")
    print(ut.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
