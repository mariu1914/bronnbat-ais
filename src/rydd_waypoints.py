"""
Rydd opp i to metodiske feil i waypoints-datasettet.

Kjor etter bygg_waypoints.py:
    python src/rydd_waypoints.py

FEIL 1: Besok avkortet av ukegrensen
    Sporene hentes per uke. Et besok som varer over et ukeskifte blir kuttet
    ved grensen og rapportert som to besok - eller som ett besok pa noyaktig
    168,0 timer (sju dogn = hele vinduet). Vi slar sammen besok pa samme
    lokalitet og fartoy som henger sammen over grensen.

FEIL 2: Dublerte lokaliteter
    Enkelte anlegg star med to lokalitetsnumre og tilnaermet identiske
    koordinater (f.eks. Skjelevika / Skjelevika1). Uten opprydding telles
    samme besok to ganger. Vi slar sammen numre som ligger naermere enn
    DUBLETT_METER fra hverandre og har liknende navn.

Skriver data/processed/waypoints_ryddet.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.visits import haversine_m

ROT = Path(__file__).resolve().parents[1]
INN = ROT / "data" / "processed"

# To besok pa samme lokalitet og fartoy regnes som ett hvis gapet er mindre
# enn dette. Ukesporene overlapper ikke, sa gapet er i praksis sekunder.
SAMMENSLA_GAP_MIN = 90.0

# Lokaliteter naermere hverandre enn dette regnes som samme anlegg.
DUBLETT_METER = 300.0

# Besok som er noyaktig sa lange er avkortet av vinduet, ikke reelle.
VINDU_TIMER = 168.0
VINDU_MARGIN = 0.5


def slå_sammen_over_ukegrenser(df: pd.DataFrame) -> pd.DataFrame:
    """Slå sammen etterfolgende besok pa samme lokalitet og fartoy."""
    df = df.sort_values(["mmsi", "lokalitet_id", "start"]).reset_index(drop=True)

    gap = (
        df["start"] - df.groupby(["mmsi", "lokalitet_id"])["slutt"].shift()
    ).dt.total_seconds() / 60.0

    ny_episode = (
        (df["mmsi"] != df["mmsi"].shift())
        | (df["lokalitet_id"] != df["lokalitet_id"].shift())
        | (gap > SAMMENSLA_GAP_MIN)
        | gap.isna()
    )
    df["episode"] = ny_episode.cumsum()

    sammenslatt = df.groupby("episode", as_index=False).agg(
        mmsi=("mmsi", "first"),
        fartoy=("fartoy", "first"),
        lokalitet_id=("lokalitet_id", "first"),
        lokalitet_navn=("lokalitet_navn", "first"),
        start=("start", "min"),
        slutt=("slutt", "max"),
        slaktemerd=("slaktemerd", "max"),
        settefisk=("settefisk", "max"),
        landbasert=("landbasert", "max"),
        kategori=("kategori", "first"),
        n_ukesbiter=("start", "size"),
    )

    sammenslatt["varighet_timer"] = (
        sammenslatt["slutt"] - sammenslatt["start"]
    ).dt.total_seconds() / 3600.0

    return sammenslatt.drop(columns=["episode"])


def finn_dubletter(lokaliteter: pd.DataFrame) -> dict[int, int]:
    """
    Finn lokalitetsnumre som peker pa samme fysiske anlegg.

    Returnerer en oppslagstabell fra dublettnummer til det laveste nummeret
    i gruppen, slik at alle besok kan mappes til én kanonisk id.
    """
    lok = lokaliteter.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    kart: dict[int, int] = {}

    for i in range(len(lok)):
        for j in range(i + 1, len(lok)):
            a, b = lok.iloc[i], lok.iloc[j]
            avstand = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            if avstand > DUBLETT_METER:
                continue

            id_a, id_b = int(a["lokalitet_id"]), int(b["lokalitet_id"])
            kanonisk = min(id_a, id_b)
            kart[max(id_a, id_b)] = kanonisk

    return kart


def main():
    fil = INN / "waypoints.csv"
    if not fil.exists():
        raise SystemExit("Mangler waypoints.csv. Kjor bygg_waypoints.py forst.")

    df = pd.read_csv(fil)
    for kol in ["start", "slutt"]:
        df[kol] = pd.to_datetime(df[kol], utc=True, format="mixed")
    for kol in ["slaktemerd", "settefisk", "landbasert"]:
        df[kol] = df[kol].astype(bool)

    # Varigheten regnes ut pa nytt, i tilfelle kildefila er redigert
    df["varighet_timer"] = (df["slutt"] - df["start"]).dt.total_seconds() / 3600.0

    print(f"Leste {len(df):,} besok\n")

    # --- FEIL 2 forst: dubletter ma kanoniseres for sammenslaing, ellers
    #     slas ikke ukesbiter registrert pa hvert sitt nummer sammen ------
    print(f"{'=' * 66}")
    print("  FEIL 2: DUBLERTE LOKALITETER")
    print(f"{'=' * 66}")

    lok_fil = INN / "lokaliteter.csv"
    if not lok_fil.exists():
        print("  lokaliteter.csv mangler - hopper over dublettsjekk.")
    else:
        lokaliteter = pd.read_csv(lok_fil)
        kart = finn_dubletter(lokaliteter)

        print(f"  Lokalitetspar naermere enn {DUBLETT_METER:.0f} m: {len(kart)}")

        if kart:
            navn = df.drop_duplicates("lokalitet_id").set_index("lokalitet_id")[
                "lokalitet_navn"
            ]
            print("\n  Sammenslatte numre:")
            for dublett, kanonisk in sorted(kart.items()):
                print(f"    {dublett} ({navn.get(dublett, '?')}) -> "
                      f"{kanonisk} ({navn.get(kanonisk, '?')})")

            for_dubl = len(df)
            df["lokalitet_id"] = df["lokalitet_id"].replace(kart)
            df = df.drop_duplicates(subset=["mmsi", "lokalitet_id", "start", "slutt"])
            print(f"\n  Fjernet {for_dubl - len(df)} dobbelttalte besok")

    # --- FEIL 1 -------------------------------------------------------
    avkortet_for = ((df["varighet_timer"] - VINDU_TIMER).abs() < VINDU_MARGIN).sum()
    print(f"\n{'=' * 66}")
    print("  FEIL 1: BESOK AVKORTET AV UKEGRENSEN")
    print(f"{'=' * 66}")
    print(f"  Besok pa ~{VINDU_TIMER:.0f} timer for opprydding : {avkortet_for}")

    for_sammensla = len(df)
    ryddet = slå_sammen_over_ukegrenser(df)
    slatt_sammen = (ryddet["n_ukesbiter"] > 1).sum()
    avkortet_etter = ((ryddet["varighet_timer"] - VINDU_TIMER).abs() < VINDU_MARGIN).sum()

    print(f"  Besok slatt sammen over ukegrense      : {slatt_sammen}")
    print(f"  Besok pa ~{VINDU_TIMER:.0f} timer etter opprydding: {avkortet_etter}")
    print(f"  Antall besok: {for_sammensla:,} -> {len(ryddet):,}")

    if avkortet_etter:
        print(f"\n  MERK: {avkortet_etter} besok ligger fortsatt pa vindusgrensen.")
        print("  Disse er trolig fortsatt avkortet. De er flagget i kolonnen")
        print("  'mulig_avkortet' slik at du kan utelate dem i analysen.")

    ryddet["mulig_avkortet"] = (
        (ryddet["varighet_timer"] - VINDU_TIMER).abs() < VINDU_MARGIN
    )

    # --- Resultat -----------------------------------------------------
    ryddet.to_csv(INN / "waypoints_ryddet.csv", index=False)

    gyldig = ryddet[~ryddet["mulig_avkortet"]]

    print(f"\n{'=' * 66}")
    print("  EFFEKT PA HOVEDFUNNET")
    print(f"{'=' * 66}")

    for navn, d in [("For opprydding", df), ("Etter opprydding", gyldig)]:
        v = d["varighet_timer"]
        p90 = v.quantile(0.90)
        andel = v[v > p90].sum() / v.sum() * 100
        print(f"  {navn:18s} n={len(d):6,}  median={v.median():5.1f}t  "
              f"p90={p90:5.1f}t  hale={andel:.0f}% av all tid")

    print(f"\nSkrevet til data/processed/waypoints_ryddet.csv")
    print("Kjor analyse_hale.py mot denne fila for oppdaterte tall.")


if __name__ == "__main__":
    main()
