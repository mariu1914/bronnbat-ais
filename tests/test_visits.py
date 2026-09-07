"""
Test av besoksdeteksjon mot syntetiske AIS-data.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.visits import finn_besok, finn_seilaser, haversine_m  # noqa: E402


def lag_syntetisk_ais():
    """
    Ett fartoy, to lokaliteter:
      1. Ligger 4 timer ved lokalitet A (i ro, innenfor radius)  -> besok
      2. Seiler 6 timer (hoy fart, langt unna)                   -> seilas
      3. Ligger 3 timer ved lokalitet B                          -> besok
      4. Passerer lokalitet A i 8 knop                           -> IKKE besok
    """
    lokaliteter = pd.DataFrame(
        {
            "lokalitet_id": [10001, 10002],
            "navn": ["Testvika", "Prøvefjorden"],
            "lat": [63.100, 63.400],
            "lon": [7.800, 8.200],
        }
    )

    rader = []
    t = pd.Timestamp("2025-03-01 06:00", tz="UTC")

    # 1. Liggetid ved A: 4 timer, posisjon hvert 10. min, ~150 m fra midtpunkt
    for i in range(25):
        rader.append((257000001, t + pd.Timedelta(minutes=10 * i), 63.1012, 7.8005, 0.2))

    # 2. Seilas: 6 timer underveis, langt fra begge lokaliteter
    t2 = t + pd.Timedelta(hours=4, minutes=30)
    for i in range(30):
        rader.append((257000001, t2 + pd.Timedelta(minutes=12 * i), 63.20 + 0.005 * i, 7.95, 11.0))

    # 3. Liggetid ved B: 3 timer
    t3 = t2 + pd.Timedelta(hours=6, minutes=30)
    for i in range(19):
        rader.append((257000001, t3 + pd.Timedelta(minutes=10 * i), 63.4008, 8.2003, 0.4))

    # 4. Passering av A i 8 knop - naer nok, men for fort
    t4 = t3 + pd.Timedelta(hours=6)
    for i in range(6):
        rader.append((257000001, t4 + pd.Timedelta(minutes=10 * i), 63.1001, 7.8001, 8.0))

    ais = pd.DataFrame(rader, columns=["mmsi", "tidspunkt", "lat", "lon", "fart_knop"])
    return ais, lokaliteter


def test_haversine_kjente_avstander():
    # ~111 km per breddegrad
    d = haversine_m(63.0, 7.0, 64.0, 7.0)
    assert 110_000 < d < 112_000

    # samme punkt
    assert haversine_m(63.0, 7.0, 63.0, 7.0) < 1


def test_finner_riktig_antall_besok():
    ais, lokaliteter = lag_syntetisk_ais()
    besok = finn_besok(ais, lokaliteter)
    assert len(besok) == 2, f"Forventet 2 besok, fikk {len(besok)}"


def test_passering_i_fart_teller_ikke():
    ais, lokaliteter = lag_syntetisk_ais()
    besok = finn_besok(ais, lokaliteter)
    # Bare ett besok ved Testvika (lokalitet A) - passeringen skal ikke telle
    assert (besok["lokalitet_id"] == 10001).sum() == 1


def test_varighet_er_rimelig():
    ais, lokaliteter = lag_syntetisk_ais()
    besok = finn_besok(ais, lokaliteter).sort_values("start")
    assert 3.8 < besok.iloc[0]["varighet_timer"] < 4.2
    assert 2.8 < besok.iloc[1]["varighet_timer"] < 3.2


def test_seilas_mellom_besok():
    ais, lokaliteter = lag_syntetisk_ais()
    besok = finn_besok(ais, lokaliteter)
    seilaser = finn_seilaser(besok)
    assert len(seilaser) == 1
    assert 6.0 < seilaser.iloc[0]["mellomrom_timer"] < 7.5


def test_kort_opphold_filtreres_bort():
    ais, lokaliteter = lag_syntetisk_ais()
    #  12 timers opphold - da skal ingenting overleve filteret
    besok = finn_besok(ais, lokaliteter, min_varighet_min=720)
    assert len(besok) == 0
