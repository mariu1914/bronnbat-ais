"""
Bygg et rent besokstabell fra de nedlastede fartoysbesokene.

Kjor etter hent_fartoysbesok.py:
    python src/bygg_besok.py

Leser cachede JSON-filer, pakker ut vesselVisits-lista, dedupliserer besok
som krysser ukegrenser, kobler pa koordinater og skriver:

    data/processed/besok_alle.csv      alle fartoyskategorier
    data/processed/besok_bronnbat.csv  kun bronnbater
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.visits import finn_seilaser

ROT = Path(__file__).resolve().parents[1]
CACHE = ROT / "data" / "raw" / "fartoysbesok"
UT = ROT / "data" / "processed"


def les_alle_besok() -> pd.DataFrame:
    """Pakk ut vesselVisits fra alle cachede filer til en flat tabell."""
    filer = sorted(CACHE.glob("*.json"))
    if not filer:
        raise SystemExit("Ingen cachede filer. Kjor hent_fartoysbesok.py forst.")

    rader = []
    for fil in filer:
        lokalitet_no = int(fil.stem.split("-")[0])
        data = json.loads(fil.read_text(encoding="utf-8"))

        if isinstance(data, dict):
            data = [data]

        for uke_rad in data:
            if not isinstance(uke_rad, dict):
                continue
            for besok in uke_rad.get("vesselVisits") or []:
                rader.append(
                    {
                        "lokalitet_id": lokalitet_no,
                        "mmsi": besok.get("mmsi"),
                        "fartoy": besok.get("vesselName"),
                        "start": besok.get("startTime"),
                        "slutt": besok.get("stopTime"),
                        "er_bronnbat": besok.get("isWellboat"),
                        "er_slaktebat": besok.get("isSlaughterBoat"),
                        "fartoystype": besok.get("shipRegisterVesselTypeNameNo"),
                        "ais_shiptype": besok.get("shipType"),
                    }
                )

    print(f"Leste {len(filer)} filer, {len(rader)} besoksrader for deduplisering")
    return pd.DataFrame(rader)


def rydd(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["mmsi", "start", "slutt"]).copy()

    df["start"] = pd.to_datetime(df["start"], utc=True, format="mixed")
    df["slutt"] = pd.to_datetime(df["slutt"], utc=True, format="mixed")
    df["mmsi"] = df["mmsi"].astype("int64")

    # Besok som krysser ukegrenser returneres i flere uker.
    for kol in ["er_bronnbat", "er_slaktebat"]:
        df[kol] = df[kol].fillna(False).astype(bool)

    for ss in ["fartoystype"]:
        df[ss] = df.groupby("mmsi")[ss].transform(lambda s: s.ffill().bfill())

    for kol in ["er_bronnbat", "er_slaktebat"]:
        df[kol] = df.groupby("mmsi")[kol].transform("max")

    df = df.drop_duplicates(subset=["lokalitet_id", "mmsi", "start", "slutt"])

    df["varighet_timer"] = (df["slutt"] - df["start"]).dt.total_seconds() / 3600.0
    df = df[df["varighet_timer"] > 0]

    return df.sort_values(["mmsi", "start"]).reset_index(drop=True)


def koble_koordinater(df: pd.DataFrame) -> pd.DataFrame:
    fil = UT / "lokaliteter.csv"
    if not fil.exists():
        print("  (lokaliteter.csv mangler - hopper over koordinater)")
        df["lokalitet_navn"] = df["lokalitet_id"].astype(str)
        return df

    lok = pd.read_csv(fil)[["lokalitet_id", "lat", "lon"]]
    df = df.merge(lok, on="lokalitet_id", how="left")
    df["lokalitet_navn"] = df["lokalitet_id"].astype(str)
    return df


def main():
    df = rydd(les_alle_besok())
    df = koble_koordinater(df)

    UT.mkdir(parents=True, exist_ok=True)
    df.to_csv(UT / "besok_alle.csv", index=False)

    bronnbat = df[df["er_bronnbat"]].copy()
    bronnbat.to_csv(UT / "besok_bronnbat.csv", index=False)

    print(f"\n{'=' * 62}")
    print(f"{len(df):6d} unike besok totalt, {df['mmsi'].nunique()} fartoy")
    print(f"{len(bronnbat):6d} bronnbatbesok, {bronnbat['mmsi'].nunique()} bronnbater")
    print(f"{df[df['er_slaktebat']]['mmsi'].nunique():6d} slaktebater")

    print("\n--- FARTOYSKATEGORIER (antall besok) ---")
    print(df["fartoystype"].fillna("(ukjent)").value_counts().head(10).to_string())

    if bronnbat.empty:
        print("\nIngen bronnbater i utvalget. Sjekk isWellboat-flagget.")
        return

    print("\n--- BRONNBATER: liggetid ---")
    per_batt = (
        bronnbat.groupby(["mmsi", "fartoy"])
        .agg(
            besok=("start", "size"),
            lokaliteter=("lokalitet_id", "nunique"),
            median_timer=("varighet_timer", "median"),
            sum_timer=("varighet_timer", "sum"),
        )
        .round(1)
        .sort_values("besok", ascending=False)
    )
    print(per_batt.head(15).to_string())

    seilaser = finn_seilaser(
        bronnbat.rename(columns={"lokalitet_navn": "lokalitet_navn"})[
            ["mmsi", "lokalitet_id", "lokalitet_navn", "start", "slutt", "varighet_timer"]
        ]
    )
    seilaser.to_csv(UT / "seilaser_bronnbat.csv", index=False)

    mellom = seilaser["mellomrom_timer"]
    print(f"\n--- TID MELLOM BESOK (bronnbater) ---")
    print(f"  antall legg     : {len(seilaser)}")
    print(f"  median          : {mellom.median():.1f} timer")
    print(f"  under 12 timer  : {(mellom < 12).mean() * 100:.0f} %")
    print(f"  over 48 timer   : {(mellom > 48).mean() * 100:.0f} %")

    print(f"\nSkrevet til data/processed/")


if __name__ == "__main__":
    main()
