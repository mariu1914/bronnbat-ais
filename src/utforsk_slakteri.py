"""
Utforsk slakteri- og fartoysspordata for vi bygger klassifiseringen.

Kjor:
    python src/utforsk_slakteri.py

Henter (1) hele slakterilista og (2) ett fartoysspor for en uke, og skriver ut
strukturen pa begge. Dette er et engangsskript for a se hva vi har a jobbe med.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.barentswatch import BarentsWatchKlient

ROT = Path(__file__).resolve().parents[1]
UT = ROT / "data" / "processed"
RAA = ROT / "data" / "raw"

AAR = 2025
TEST_UKE = 33  # hoysesong ifolge sesongprofilen


def vis_struktur(navn: str, data, maks_nokler: int = 25):
    print(f"\n{'=' * 64}")
    print(f"  {navn}")
    print(f"{'=' * 64}")

    if isinstance(data, dict):
        print(f"Type: dict med noklene: {list(data.keys())[:maks_nokler]}")
        for nokkel, verdi in list(data.items())[:maks_nokler]:
            if isinstance(verdi, list):
                print(f"  {nokkel:30s} liste med {len(verdi)} elementer")
                if verdi and isinstance(verdi[0], dict):
                    print(f"    forste element: {list(verdi[0].keys())}")
            else:
                print(f"  {nokkel:30s} {str(verdi)[:50]}")
        return

    if isinstance(data, list):
        print(f"Type: liste med {len(data)} elementer")
        if data and isinstance(data[0], dict):
            print(f"\nFelter i forste element:")
            for nokkel, verdi in data[0].items():
                print(f"  {nokkel:32s} {str(verdi)[:45]}")
        return

    print(f"Type: {type(data).__name__} - {str(data)[:200]}")


def main():
    bw = BarentsWatchKlient()
    RAA.mkdir(parents=True, exist_ok=True)

    # --- 1. Slakterier -------------------------------------------------
    try:
        slakterier = bw.get("/bwapi/v1/geodata/fishslaughterhouses")
        (RAA / "slakterier.json").write_text(
            json.dumps(slakterier, ensure_ascii=False), encoding="utf-8"
        )
        vis_struktur("SLAKTERIER  /v1/geodata/fishslaughterhouses", slakterier)

        # Prov a lage en tabell hvis strukturen tillater det
        liste = slakterier
        if isinstance(liste, dict):
            for n in ("slaughterhouses", "data", "items"):
                if n in liste:
                    liste = liste[n]
                    break

        if isinstance(liste, list) and liste and isinstance(liste[0], dict):
            df = pd.json_normalize(liste)
            print(f"\nAntall slakterier: {len(df)}")

            lat_kol = [k for k in df.columns if "lat" in k.lower()]
            lon_kol = [k for k in df.columns if "lon" in k.lower()]
            print(f"Koordinatkolonner: {lat_kol} / {lon_kol}")

            UT.mkdir(parents=True, exist_ok=True)
            df.to_csv(UT / "slakterier_raa.csv", index=False)
            print("Skrevet til data/processed/slakterier_raa.csv")

    except Exception as feil:
        print(f"\nSLAKTERIER FEILET: {feil}")

    # --- 2. Fartoysspor ------------------------------------------------
    besok_fil = UT / "besok_bronnbat.csv"
    if not besok_fil.exists():
        print("\nMangler besok_bronnbat.csv - hopper over fartoysspor.")
        return

    besok = pd.read_csv(besok_fil)
    # Velg den mest aktive bronnbaten som testfartoy
    mmsi = int(besok["mmsi"].value_counts().idxmax())
    navn = besok.loc[besok["mmsi"] == mmsi, "fartoy"].iloc[0]
    print(f"\n\nTestfartoy: {navn} (MMSI {mmsi}), uke {TEST_UKE}")

    try:
        spor = bw.get(f"/bwapi/v1/geodata/fishhealth/vesseltrack/{mmsi}/{AAR}/{TEST_UKE}")
        (RAA / f"vesseltrack_{mmsi}_{AAR}_{TEST_UKE}.json").write_text(
            json.dumps(spor, ensure_ascii=False), encoding="utf-8"
        )
        vis_struktur(
            f"FARTOYSSPOR  /v1/geodata/fishhealth/vesseltrack/{{mmsi}}/{{ar}}/{{uke}}",
            spor,
        )
    except Exception as feil:
        print(f"\nFARTOYSSPOR FEILET: {feil}")


if __name__ == "__main__":
    main()
