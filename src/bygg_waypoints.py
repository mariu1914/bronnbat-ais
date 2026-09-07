"""

"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROT = Path(__file__).resolve().parents[1]
CACHE = ROT / "data" / "raw" / "spor"
UT = ROT / "data" / "processed"

AAR = 2025


def les_waypoints() -> pd.DataFrame:
    filer = sorted(CACHE.glob("*.json"))
    if not filer:
        raise SystemExit("Ingen cachede sporfiler. Kjor hent_spor.py forst.")

    rader = []
    for fil in filer:
        try:
            data = json.loads(fil.read_text(encoding="utf-8"))
        except Exception:
            continue

        mmsi = data.get("mmsi")
        navn = data.get("vesselName")
        uke = data.get("week")

        for wp in (data.get("trackAnalysis") or {}).get("localityWaypoints") or []:
            if not isinstance(wp, dict):
                continue
            sykdommer = wp.get("diseases") or []
            rader.append(
                {
                    "mmsi": mmsi,
                    "fartoy": navn,
                    "uke": uke,
                    "lokalitet_id": wp.get("localityNo"),
                    "lokalitet_navn": wp.get("name"),
                    "start": wp.get("fromTime"),
                    "slutt": wp.get("toTime"),
                    "slaktemerd": wp.get("isSlaughterHoldingCage"),
                    "settefisk": wp.get("isJuvenile"),
                    "landbasert": wp.get("isOnLand"),
                    "n_sykdommer": len(sykdommer) if isinstance(sykdommer, list) else 0,
                }
            )

    print(f"Leste {len(filer)} filer, {len(rader)} waypoints for deduplisering")
    return pd.DataFrame(rader)


def rydd(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["mmsi", "start", "slutt", "lokalitet_id"]).copy()

    df["start"] = pd.to_datetime(df["start"], utc=True, format="mixed")
    df["slutt"] = pd.to_datetime(df["slutt"], utc=True, format="mixed")
    df["mmsi"] = df["mmsi"].astype("int64")
    df["lokalitet_id"] = df["lokalitet_id"].astype("int64")

    for kol in ["slaktemerd", "settefisk", "landbasert"]:
        df[kol] = df[kol].fillna(False).astype(bool)

    # Besok som krysser ukegrenser rapporteres i flere uker
    df = df.drop_duplicates(subset=["mmsi", "lokalitet_id", "start", "slutt"])

    df["varighet_timer"] = (df["slutt"] - df["start"]).dt.total_seconds() / 3600.0
    df = df[df["varighet_timer"] > 0]

    df["kategori"] = "ordinaer merd"
    df.loc[df["settefisk"], "kategori"] = "settefisk"
    df.loc[df["slaktemerd"], "kategori"] = "slaktemerd"
    df.loc[df["landbasert"], "kategori"] = "landbasert"

    return df.sort_values(["mmsi", "start"]).reset_index(drop=True)


def main():
    df = rydd(les_waypoints())
    UT.mkdir(parents=True, exist_ok=True)

    df.to_csv(UT / "waypoints.csv", index=False)

    navn = (
        df.dropna(subset=["lokalitet_navn"])
        .groupby("lokalitet_id")["lokalitet_navn"]
        .agg(lambda s: s.value_counts().idxmax())
        .reset_index()
    )
    navn.to_csv(UT / "lokalitetsnavn.csv", index=False)

    i_aar = df[df["start"].dt.year == AAR]

    print(f"\n{'=' * 64}")
    print(f"{len(df)} unike besok, {df['mmsi'].nunique()} fartoy, "
          f"{df['lokalitet_id'].nunique()} lokaliteter")
    print(f"{len(navn)} lokalitetsnavn hentet ut")
    print(f"{len(i_aar)} besok i {AAR}")

    print(f"\n--- LIGGETID PER BESOKSTYPE ({AAR}) ---")
    per_kat = (
        i_aar.groupby("kategori")
        .agg(
            besok=("start", "size"),
            median_timer=("varighet_timer", "median"),
            snitt_timer=("varighet_timer", "mean"),
            sum_timer=("varighet_timer", "sum"),
        )
        .round(1)
        .sort_values("besok", ascending=False)
    )
    per_kat["andel_av_besok"] = (per_kat["besok"] / len(i_aar) * 100).round(1)
    print(per_kat.to_string())

    print(f"\n--- MEST BESOKTE LOKALITETER ({AAR}) ---")
    topp = (
        i_aar.groupby(["lokalitet_id", "lokalitet_navn"])
        .agg(besok=("start", "size"), fartoy=("mmsi", "nunique"),
             median_timer=("varighet_timer", "median"))
        .round(1)
        .sort_values("besok", ascending=False)
        .head(12)
    )
    print(topp.to_string())

    print(f"\n--- FARTOY MED HOYEST ANDEL SLAKTEMERD ---")
    andel = (
        i_aar.groupby("fartoy")
        .agg(besok=("start", "size"),
             andel_slaktemerd=("slaktemerd", "mean"),
             median_timer=("varighet_timer", "median"))
    )
    andel = andel[andel["besok"] >= 30]
    andel["andel_slaktemerd"] = (andel["andel_slaktemerd"] * 100).round(1)
    print(andel.round(1).sort_values("andel_slaktemerd", ascending=False).head(12).to_string())

    print(f"\nSkrevet til data/processed/waypoints.csv og lokalitetsnavn.csv")


if __name__ == "__main__":
    main()
