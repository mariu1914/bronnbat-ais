"""
Bygg slakteriregister og undersok strukturen pa fartoysporpunkter.

Kjor etter utforsk_slakteri.py:
    python src/bygg_slakterier.py

1. Pakker ut koordinater fra GeoJSON og skriver data/processed/slakterier.csv
   i samme format som lokaliteter.csv, slik at finn_besok() kan brukes rett pa
   det.
2. Leser det cachede fartoysporet fra disk og viser hvilke felter et
   posisjonspunkt har. Ingen nye API-kall.

Alle 104 slakterier beholdes. Bronnbater seiler langt, og filtrerer vi
geografisk risikerer vi a miste anlop vi burde fanget.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROT = Path(__file__).resolve().parents[1]
RAA = ROT / "data" / "raw"
UT = ROT / "data" / "processed"


def hent_koordinat(geometry) -> tuple[float | None, float | None]:
    """
    GeoJSON Point: coordinates er [lon, lat] - motsatt rekkefolge av
    hva folk flest forventer. Feil her gir punkter midt i Sibir.
    """
    if not isinstance(geometry, dict):
        return None, None

    koord = geometry.get("coordinates")
    if not isinstance(koord, (list, tuple)) or len(koord) < 2:
        return None, None

    lon, lat = koord[0], koord[1]
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def bygg_register():
    fil = RAA / "slakterier.json"
    if not fil.exists():
        raise SystemExit("Mangler slakterier.json. Kjor utforsk_slakteri.py forst.")

    data = json.loads(fil.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for n in ("slaughterhouses", "data", "items"):
            if n in data:
                data = data[n]
                break

    rader = []
    for s in data:
        lat, lon = hent_koordinat(s.get("geometry"))
        if lat is None:
            continue
        rader.append(
            {
                "lokalitet_id": s.get("approvalNumber") or s.get("id"),
                "navn": s.get("establishment"),
                "lat": lat,
                "lon": lon,
                "selskap": s.get("company"),
                "gyldig_til": s.get("validTo"),
            }
        )

    df = pd.DataFrame(rader)

    # Nedlagte anlegg har validTo satt. De ma vaere med hvis de var i drift
    # i analysearet, sa vi merker dem i stedet for a fjerne dem.
    df["aktiv"] = df["gyldig_til"].isna()

    UT.mkdir(parents=True, exist_ok=True)
    df.to_csv(UT / "slakterier.csv", index=False)

    print(f"{len(df)} slakterier med koordinater ({df['aktiv'].sum()} aktive)")
    print(f"  breddegrad: {df['lat'].min():.2f} - {df['lat'].max():.2f}")
    print(f"  lengdegrad: {df['lon'].min():.2f} - {df['lon'].max():.2f}")

    # Fornuftssjekk: Norge ligger grovt mellom 57-72 N og 4-32 O
    rart = df[(df["lat"] < 57) | (df["lat"] > 72) | (df["lon"] < 3) | (df["lon"] > 33)]
    if len(rart):
        print(f"\n  ADVARSEL: {len(rart)} punkter utenfor Norge - lat/lon kan vaere byttet om")
    else:
        print("  Alle punkter ligger innenfor Norge - koordinatrekkefolgen er riktig")

    naer = df[(df["lat"].between(62.6, 64.2)) & (df["lon"].between(6.8, 9.5))]
    print(f"\n{len(naer)} slakterier i Nordmore-omradet:")
    for _, r in naer.iterrows():
        print(f"  {str(r['navn'])[:45]:47s} {r['lat']:.4f}, {r['lon']:.4f}")

    print("\nSkrevet til data/processed/slakterier.csv")


def vis_punktstruktur():
    filer = sorted(RAA.glob("vesseltrack_*.json"))
    if not filer:
        print("\nFant ingen cachet vesseltrack-fil.")
        return

    data = json.loads(filer[0].read_text(encoding="utf-8"))
    spor = data.get("vesselTracks") or []

    print(f"\n{'=' * 64}")
    print(f"  FARTOYSSPOR: {filer[0].name}")
    print(f"{'=' * 64}")
    print(f"{len(spor)} sporsegmenter")

    for i, segment in enumerate(spor[:2]):
        punkter = segment.get("points") or []
        print(f"\nSegment {i}: {segment.get('fromTime')} -> {segment.get('toTime')}")
        print(f"  isNoSignal: {segment.get('isNoSignal')}, {len(punkter)} punkter")

        if punkter:
            forste = punkter[0]
            if isinstance(forste, dict):
                print("  Felter i et punkt:")
                for nokkel, verdi in forste.items():
                    print(f"    {nokkel:26s} {str(verdi)[:45]}")
            else:
                print(f"  Punkt er ikke dict, men {type(forste).__name__}: {str(forste)[:80]}")

    analyse = data.get("trackAnalysis")
    if isinstance(analyse, dict):
        print(f"\ntrackAnalysis-felter: {list(analyse.keys())}")


if __name__ == "__main__":
    bygg_register()
    vis_punktstruktur()
