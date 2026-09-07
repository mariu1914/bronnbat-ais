"""
Lag figurene til README.

Kjor etter bygg_besok.py:
    python src/figurer.py

Skriver PNG-filer til output/figures/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROT = Path(__file__).resolve().parents[1]
INN = ROT / "data" / "processed"
FIG = ROT / "output" / "figures"

BLA = "#2d5f8a"
GRA = "#9aa5b1"
AKSENT = "#c1553b"

plt.rcParams.update({
    "figure.dpi": 150,
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "-",
    "axes.axisbelow": True,
})


def last() -> tuple[pd.DataFrame, pd.DataFrame]:
    besok_fil = INN / "besok_bronnbat.csv"
    if not besok_fil.exists():
        raise SystemExit("Mangler besok_bronnbat.csv. Kjor bygg_besok.py forst.")

    besok = pd.read_csv(besok_fil, parse_dates=["start", "slutt"])

    seilas_fil = INN / "seilaser_bronnbat.csv"
    seilaser = (
        pd.read_csv(seilas_fil, parse_dates=["avgang", "ankomst"])
        if seilas_fil.exists()
        else pd.DataFrame()
    )
    return besok, seilaser


def fig_liggetid(besok: pd.DataFrame):
    """Fordeling av liggetid - viser at det finnes flere operasjonsmoduser."""
    fig, ax = plt.subplots(figsize=(7, 3.6))

    data = besok["varighet_timer"].clip(upper=48)
    ax.hist(data, bins=48, color=BLA, edgecolor="white", linewidth=0.4)

    median = besok["varighet_timer"].median()
    ax.axvline(median, color=AKSENT, linewidth=1.6, linestyle="--")
    ax.text(median + 0.8, ax.get_ylim()[1] * 0.9,
            f"median {median:.1f} t", color=AKSENT, fontsize=8.5)

    ax.set_xlabel("Liggetid ved lokalitet (timer, kappet ved 48)")
    ax.set_ylabel("Antall besøk")
    ax.set_title("Brønnbåtbesøk fordelt etter liggetid", loc="left", fontweight="bold")

    fig.tight_layout()
    fig.savefig(FIG / "liggetid_fordeling.png")
    plt.close(fig)


def fig_per_fartoy(besok: pd.DataFrame, n=15):
    """Medianliggetid per fartoy - spredningen er hovedpoenget."""
    per = (
        besok.groupby("fartoy")
        .agg(besok=("start", "size"), median=("varighet_timer", "median"))
        .sort_values("besok", ascending=False)
        .head(n)
        .sort_values("median")
    )

    fig, ax = plt.subplots(figsize=(7, 4.6))
    farger = [AKSENT if v > per["median"].median() else BLA for v in per["median"]]
    ax.barh(per.index, per["median"], color=farger, height=0.7)

    for navn, rad in per.iterrows():
        ax.text(rad["median"] + 0.15, navn, f"{rad['median']:.1f} t  ({int(rad['besok'])})",
                va="center", fontsize=7.5, color="#444")

    ax.set_xlabel("Median liggetid (timer). Antall besøk i parentes.")
    ax.set_title(f"Medianliggetid per brønnbåt, {n} mest aktive",
                 loc="left", fontweight="bold")
    ax.set_xlim(0, per["median"].max() * 1.35)

    fig.tight_layout()
    fig.savefig(FIG / "liggetid_per_fartoy.png")
    plt.close(fig)


def fig_sesong(besok: pd.DataFrame):
    """Aktivitet gjennom aret."""
    b = besok.copy()
    b["maaned"] = b["start"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()

    per = b.groupby("maaned").agg(
        besok=("start", "size"),
        fartoy=("mmsi", "nunique"),
    )

    fig, ax1 = plt.subplots(figsize=(7, 3.6))
    ax1.bar(per.index, per["besok"], width=22, color=BLA, label="Besøk")
    ax1.set_ylabel("Antall besøk", color=BLA)
    ax1.tick_params(axis="y", labelcolor=BLA)

    ax2 = ax1.twinx()
    ax2.plot(per.index, per["fartoy"], color=AKSENT, marker="o",
             markersize=4, linewidth=1.6, label="Aktive fartøy")
    ax2.set_ylabel("Aktive brønnbåter", color=AKSENT)
    ax2.tick_params(axis="y", labelcolor=AKSENT)
    ax2.grid(False)
    ax2.set_ylim(0, per["fartoy"].max() * 1.3)

    ax1.set_title("Brønnbåtaktivitet gjennom året", loc="left", fontweight="bold")
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout()
    fig.savefig(FIG / "sesongprofil.png")
    plt.close(fig)


def fig_mellomrom(seilaser: pd.DataFrame):
    """Tid mellom besok. NB: ikke det samme som seilingstid."""
    if seilaser.empty:
        return

    fig, ax = plt.subplots(figsize=(7, 3.6))
    data = seilaser["mellomrom_timer"].clip(lower=0, upper=96)
    ax.hist(data, bins=48, color=GRA, edgecolor="white", linewidth=0.4)

    median = seilaser["mellomrom_timer"].median()
    ax.axvline(median, color=AKSENT, linewidth=1.6, linestyle="--")
    ax.text(median + 1.5, ax.get_ylim()[1] * 0.9,
            f"median {median:.1f} t", color=AKSENT, fontsize=8.5)

    ax.set_xlabel("Timer mellom to lokalitetsbesøk (kappet ved 96)")
    ax.set_ylabel("Antall")
    ax.set_title("Tid mellom besøk — inkluderer seilas, havn, venting og verft",
                 loc="left", fontweight="bold")

    fig.tight_layout()
    fig.savefig(FIG / "mellom_besok.png")
    plt.close(fig)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    besok, seilaser = last()

    print(f"{len(besok)} brønnbåtbesøk, {besok['mmsi'].nunique()} fartøy\n")

    fig_liggetid(besok)
    fig_per_fartoy(besok)
    fig_sesong(besok)
    fig_mellomrom(seilaser)

    for fil in sorted(FIG.glob("*.png")):
        print(f"  {fil.relative_to(ROT)}")

    print("\n--- TALL TIL README ---")
    print(f"  brønnbåter          : {besok['mmsi'].nunique()}")
    print(f"  besøk               : {len(besok)}")
    print(f"  lokaliteter besøkt  : {besok['lokalitet_id'].nunique()}")
    print(f"  median liggetid     : {besok['varighet_timer'].median():.1f} timer")
    print(f"  andel under 4 timer : {(besok['varighet_timer'] < 4).mean() * 100:.0f} %")
    print(f"  andel over 12 timer : {(besok['varighet_timer'] > 12).mean() * 100:.0f} %")


if __name__ == "__main__":
    main()
