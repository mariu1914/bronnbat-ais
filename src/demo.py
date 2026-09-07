"""
Kjorbar demo pa syntetiske data.

"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.metrics import fartoysstatistikk, lokalitetsstatistikk, maanedsprofil
from src.visits import finn_besok, finn_seilaser

ROT = Path(__file__).resolve().parents[1]


def lag_syntetisk_flate(n_fartoy=6, n_lokaliteter=14, dager=90, frø=42):
    """Fiktiv bronnbatflate pa Nordmore. IKKE ekte data - kun for testing."""
    rng = np.random.default_rng(frø)

    lokaliteter = pd.DataFrame(
        {
            "lokalitet_id": np.arange(20001, 20001 + n_lokaliteter),
            "navn": [f"Lokalitet {i + 1}" for i in range(n_lokaliteter)],
            "lat": rng.uniform(62.9, 63.6, n_lokaliteter),
            "lon": rng.uniform(7.3, 8.6, n_lokaliteter),
        }
    )

    rader = []
    start = pd.Timestamp("2025-01-01", tz="UTC")

    for k in range(n_fartoy):
        mmsi = 257100000 + k
        t = start + pd.Timedelta(hours=float(rng.uniform(0, 48)))
        slutt = start + pd.Timedelta(days=dager)

        while t < slutt:
            lok = lokaliteter.iloc[rng.integers(0, n_lokaliteter)]

            # Liggetid ved lokalitet: typisk 3-14 timer
            liggetid = float(rng.uniform(3, 14))
            n_pos = max(2, int(liggetid * 6))
            for i in range(n_pos):
                rader.append(
                    (
                        mmsi,
                        t + pd.Timedelta(hours=liggetid * i / n_pos),
                        lok["lat"] + rng.normal(0, 0.0012),
                        lok["lon"] + rng.normal(0, 0.0012),
                        abs(rng.normal(0.2, 0.15)),
                    )
                )
            t += pd.Timedelta(hours=liggetid)

            # Seilas / annet opphold: 4-30 timer, langt fra lokalitetene
            seilas = float(rng.uniform(4, 30))
            n_pos = max(2, int(seilas * 4))
            for i in range(n_pos):
                rader.append(
                    (
                        mmsi,
                        t + pd.Timedelta(hours=seilas * i / n_pos),
                        62.4 + rng.normal(0, 0.05),
                        6.5 + rng.normal(0, 0.05),
                        float(rng.uniform(8, 13)),
                    )
                )
            t += pd.Timedelta(hours=seilas)

    ais = pd.DataFrame(rader, columns=["mmsi", "tidspunkt", "lat", "lon", "fart_knop"])
    return ais, lokaliteter


def main():
    print("Genererer syntetisk flate (IKKE ekte data) ...")
    ais, lokaliteter = lag_syntetisk_flate()
    print(f"  {len(ais):,} AIS-posisjoner, {ais['mmsi'].nunique()} fartoy, "
          f"{len(lokaliteter)} lokaliteter\n")

    besok = finn_besok(ais, lokaliteter)
    seilaser = finn_seilaser(besok)
    print(f"Fant {len(besok)} lokalitetsbesok og {len(seilaser)} mellomliggende seilaser\n")

    per_fartoy = fartoysstatistikk(besok, seilaser)
    per_lokalitet = lokalitetsstatistikk(besok)
    per_maaned = maanedsprofil(besok)

    print("--- Per fartoy ---")
    print(
        per_fartoy[
            ["mmsi", "n_besok", "median_liggetid_timer", "andel_ved_lokalitet"]
        ].round(2).to_string(index=False)
    )

    print("\n--- Topp 5 lokaliteter ---")
    print(per_lokalitet.head(5).round(1).to_string(index=False))

    ut = ROT / "data" / "processed"
    ut.mkdir(parents=True, exist_ok=True)
    besok.to_csv(ut / "besok.csv", index=False)
    seilaser.to_csv(ut / "seilaser.csv", index=False)
    per_fartoy.to_csv(ut / "fartoysstatistikk.csv", index=False)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, akser = plt.subplots(1, 2, figsize=(11, 4.2))

        akser[0].hist(besok["varighet_timer"], bins=30, color="#3b6ea5", edgecolor="white")
        akser[0].set_xlabel("Liggetid ved lokalitet (timer)")
        akser[0].set_ylabel("Antall besok")
        akser[0].set_title("Fordeling av liggetid")

        akser[1].bar(
            per_fartoy["mmsi"].astype(str),
            per_fartoy["andel_ved_lokalitet"],
            color="#3b6ea5",
        )
        akser[1].set_ylabel("Andel av tid ved lokalitet")
        akser[1].set_title("Per fartoy")
        akser[1].tick_params(axis="x", rotation=45)

        fig.suptitle("SYNTETISKE DATA - kun for testing av pipeline", fontsize=9)
        fig.tight_layout()

        figur = ROT / "output" / "figures" / "demo.png"
        figur.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(figur, dpi=140)
        print(f"\nFigur skrevet til {figur.relative_to(ROT)}")
    except ImportError:
        print("\n(matplotlib ikke installert - hopper over figur)")

    print(f"Tabeller skrevet til {ut.relative_to(ROT)}/")


if __name__ == "__main__":
    main()
