"""
Haleanalyse: hva kjennetegner de lengste besokene?

Kjor etter bygg_waypoints.py:
    python src/analyse_hale.py

Bakgrunn: ordinaere merdbesok har median 3,0 timer men snitt 6,9. Den
forskjellen betyr at fa, svaert lange besok drar snittet opp. Sporsmalet er
hva de lange besokene faktisk er.

Skriptet gjor to ting:
  1. Deler besokene i persentilgrupper og ser hva som skiller toppen fra bunnen
  2. Regner ut hvor stor andel av flatens tid som ligger pa Nordmore
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROT = Path(__file__).resolve().parents[1]
INN = ROT / "data" / "processed"

AAR = 2025

# Grensen for "lange besok". P90 = de 10 prosent lengste.
HALE_PERSENTIL = 0.90


def last() -> tuple[pd.DataFrame, set[int]]:
    # Bruk den ryddede fila hvis den finnes - den har slatt sammen besok
    # over ukegrenser og fjernet dublerte lokaliteter.
    ryddet_fil = INN / "waypoints_ryddet.csv"
    raa_fil = INN / "waypoints.csv"

    if ryddet_fil.exists():
        fil = ryddet_fil
        print(f"Bruker {fil.name} (ryddet)")
    elif raa_fil.exists():
        fil = raa_fil
        print(f"Bruker {fil.name} - kjor rydd_waypoints.py for renere tall")
    else:
        raise SystemExit("Mangler waypoints.csv. Kjor bygg_waypoints.py forst.")

    df = pd.read_csv(fil)
    for kol in ["start", "slutt"]:
        df[kol] = pd.to_datetime(df[kol], utc=True, format="mixed")
    df["varighet_timer"] = (df["slutt"] - df["start"]).dt.total_seconds() / 3600.0

    df = df[df["start"].dt.year == AAR].copy()

    # Besok som fortsatt ligger pa vindusgrensen er avkortet, ikke reelle
    if "mulig_avkortet" in df.columns:
        avkortet = df["mulig_avkortet"].astype(bool)
        if avkortet.any():
            print(f"  Utelater {avkortet.sum()} besok flagget som avkortet")
            df = df[~avkortet]

    lok_fil = INN / "lokaliteter.csv"
    nordmore = set()
    if lok_fil.exists():
        nordmore = set(pd.read_csv(lok_fil)["lokalitet_id"].astype(int))
    else:
        print("  (lokaliteter.csv mangler - hopper over Nordmore-avgrensning)")

    df["nordmore"] = df["lokalitet_id"].isin(nordmore)
    return df, nordmore


def persentilprofil(df: pd.DataFrame):
    """Del besokene i grupper og se hva som endrer seg oppover i fordelingen."""
    print(f"\n{'=' * 70}")
    print("  FORDELING AV LIGGETID")
    print(f"{'=' * 70}")

    kvantiler = [0.5, 0.75, 0.9, 0.95, 0.99, 1.0]
    v = df["varighet_timer"]
    print(f"  antall besok : {len(df):,}")
    print(f"  median       : {v.median():.1f} t")
    print(f"  snitt        : {v.mean():.1f} t")
    for q in kvantiler:
        print(f"  p{int(q * 100):<3d}         : {v.quantile(q):.1f} t")

    grense = v.quantile(HALE_PERSENTIL)
    df = df.copy()
    df["gruppe"] = pd.cut(
        v,
        bins=[0, v.quantile(0.5), v.quantile(0.75), grense, float("inf")],
        labels=["korteste 50%", "50-75%", "75-90%", f"lengste 10% (>{grense:.0f}t)"],
    )

    print(f"\n--- HVA UTGJOR HVER GRUPPE ---")
    profil = df.groupby("gruppe", observed=True).agg(
        besok=("start", "size"),
        median_timer=("varighet_timer", "median"),
        sum_timer=("varighet_timer", "sum"),
        andel_slaktemerd=("slaktemerd", "mean"),
        andel_landbasert=("landbasert", "mean"),
        andel_nordmore=("nordmore", "mean"),
        n_fartoy=("mmsi", "nunique"),
        n_lokaliteter=("lokalitet_id", "nunique"),
    )
    profil["andel_av_all_tid"] = profil["sum_timer"] / df["varighet_timer"].sum()
    for kol in ["andel_slaktemerd", "andel_landbasert", "andel_nordmore", "andel_av_all_tid"]:
        profil[kol] = (profil[kol] * 100).round(1)

    print(profil.round(1).to_string())

    andel_tid = profil.iloc[-1]["andel_av_all_tid"]
    print(f"\n  De 10 prosent lengste besokene star for {andel_tid:.0f} % av all liggetid.")

    return df, grense


def hva_kjennetegner_halen(df: pd.DataFrame, grense: float):
    hale = df[df["varighet_timer"] > grense]
    resten = df[df["varighet_timer"] <= grense]

    print(f"\n{'=' * 70}")
    print(f"  DE LENGSTE BESOKENE (over {grense:.0f} timer)")
    print(f"{'=' * 70}")

    print("\n--- Besokstype ---")
    sam = pd.DataFrame({
        "hale_%": hale["kategori"].value_counts(normalize=True) * 100,
        "ovrige_%": resten["kategori"].value_counts(normalize=True) * 100,
    }).fillna(0).round(1)
    sam["differanse"] = (sam["hale_%"] - sam["ovrige_%"]).round(1)
    print(sam.to_string())

    print("\n--- Maned ---")
    hale_m = hale["start"].dt.month.value_counts(normalize=True).sort_index() * 100
    alle_m = df["start"].dt.month.value_counts(normalize=True).sort_index() * 100
    maaned = pd.DataFrame({"hale_%": hale_m, "alle_%": alle_m}).fillna(0)
    maaned["overrepr"] = (maaned["hale_%"] - maaned["alle_%"]).round(1)
    print(maaned.round(1).to_string())

    print("\n--- Fartoy med flest lange besok ---")
    per_bat = pd.DataFrame({
        "lange_besok": hale.groupby("fartoy").size(),
        "alle_besok": df.groupby("fartoy").size(),
    }).fillna(0)
    per_bat["andel_%"] = (per_bat["lange_besok"] / per_bat["alle_besok"] * 100).round(1)
    per_bat = per_bat[per_bat["alle_besok"] >= 50]
    print(per_bat.sort_values("andel_%", ascending=False).head(10).to_string())

    print("\n--- Lokaliteter med flest lange besok ---")
    per_lok = (
        hale.groupby(["lokalitet_id", "lokalitet_navn"])
        .agg(lange_besok=("start", "size"),
             median_timer=("varighet_timer", "median"),
             n_fartoy=("mmsi", "nunique"))
        .sort_values("lange_besok", ascending=False)
        .head(12)
    )
    print(per_lok.round(1).to_string())

    print("\n--- Aller lengste enkeltbesok ---")
    topp = hale.nlargest(10, "varighet_timer")[
        ["fartoy", "lokalitet_navn", "kategori", "start", "varighet_timer"]
    ].copy()
    topp["start"] = topp["start"].dt.strftime("%Y-%m-%d %H:%M")
    topp["varighet_timer"] = topp["varighet_timer"].round(1)
    print(topp.to_string(index=False))


def nordmore_andel(df: pd.DataFrame, nordmore: set[int]):
    if not nordmore:
        return

    print(f"\n{'=' * 70}")
    print("  HVOR MYE AV FLATENS TID LIGGER PA NORDMORE?")
    print(f"{'=' * 70}")

    tid_i = df[df["nordmore"]]["varighet_timer"].sum()
    tid_ute = df[~df["nordmore"]]["varighet_timer"].sum()
    besok_i = df["nordmore"].sum()

    print(f"  Lokaliteter i utvalget      : {len(nordmore)}")
    print(f"  Besok pa Nordmore           : {besok_i:,} av {len(df):,} "
          f"({besok_i / len(df) * 100:.1f} %)")
    print(f"  Liggetid pa Nordmore        : {tid_i:,.0f} timer "
          f"({tid_i / (tid_i + tid_ute) * 100:.1f} %)")
    print(f"  Liggetid ovrige regioner    : {tid_ute:,.0f} timer")

    print(f"\n--- Fartoy etter tilknytning til regionen ---")
    per_bat = df.groupby("fartoy").agg(
        besok=("start", "size"),
        andel_nordmore=("nordmore", "mean"),
        timer_nordmore=("varighet_timer", lambda s: s[df.loc[s.index, "nordmore"]].sum()),
    )
    per_bat["andel_nordmore"] = (per_bat["andel_nordmore"] * 100).round(1)
    per_bat = per_bat[per_bat["besok"] >= 30].sort_values("andel_nordmore", ascending=False)

    print(f"\n  Mest lokale ({len(per_bat)} fartoy med minst 30 besok):")
    print(per_bat.head(8).round(1).to_string())
    print(f"\n  Minst lokale:")
    print(per_bat.tail(5).round(1).to_string())

    lokale = (per_bat["andel_nordmore"] > 50).sum()
    print(f"\n  {lokale} av {len(per_bat)} fartoy har over halvparten av besokene sine "
          f"pa Nordmore.")


def main():
    df, nordmore = last()
    df, grense = persentilprofil(df)
    hva_kjennetegner_halen(df, grense)
    nordmore_andel(df, nordmore)


if __name__ == "__main__":
    main()
