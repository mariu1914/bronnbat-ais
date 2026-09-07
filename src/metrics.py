"""
Nokkeltall utledet fra lokalitetsbesok og seilaser.

Alle tall her er *proxyer*. AIS forteller hvor fartoyet er, ikke hva det gjor
eller om det har last om bord. Skriv det i README-en, og vaer presis pa
hva du faktisk maler.
"""

from __future__ import annotations

import pandas as pd


def fartoysstatistikk(besok: pd.DataFrame, seilaser: pd.DataFrame) -> pd.DataFrame:
    """
    Per fartoy: hvor mye av observert tid gar med til opphold ved lokalitet,
    og hvor mye til alt annet (seilas, havn, venting, verft).

    "utnyttelsesgrad" her = andel av tiden fartoyet ligger ved en
    oppdrettslokalitet. Det er en operasjonell proxy, ikke et mal pa
    inntjening. Et rederi vil kanskje si det motsatte: kort liggetid er bra.
    Diskuter dette eksplisitt i rapporten - det viser at du forstar bransjen.
    """
    per_fartoy = besok.groupby("mmsi").agg(
        n_besok=("start", "size"),
        timer_ved_lokalitet=("varighet_timer", "sum"),
        median_liggetid_timer=("varighet_timer", "median"),
        forste_obs=("start", "min"),
        siste_obs=("slutt", "max"),
        n_unike_lokaliteter=("lokalitet_id", "nunique"),
    )

    per_fartoy["observert_tid_timer"] = (
        per_fartoy["siste_obs"] - per_fartoy["forste_obs"]
    ).dt.total_seconds() / 3600.0

    mellomrom = seilaser.groupby("mmsi")["mellomrom_timer"].sum()
    per_fartoy["timer_mellom_besok"] = mellomrom.reindex(per_fartoy.index).fillna(0.0)

    per_fartoy["andel_ved_lokalitet"] = (
        per_fartoy["timer_ved_lokalitet"] / per_fartoy["observert_tid_timer"]
    )

    return per_fartoy.reset_index()


def lokalitetsstatistikk(besok: pd.DataFrame) -> pd.DataFrame:
    """Per lokalitet: hvor ofte besokt, av hvor mange fartoy, hvor lenge."""
    return (
        besok.groupby(["lokalitet_id", "lokalitet_navn"])
        .agg(
            n_besok=("start", "size"),
            n_fartoy=("mmsi", "nunique"),
            sum_liggetid_timer=("varighet_timer", "sum"),
            median_liggetid_timer=("varighet_timer", "median"),
        )
        .reset_index()
        .sort_values("n_besok", ascending=False)
    )


def maanedsprofil(besok: pd.DataFrame) -> pd.DataFrame:
    """Sesongvariasjon: antall besok og samlet liggetid per maned."""
    b = besok.copy()
    b["maaned"] = b["start"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
    return (
        b.groupby("maaned")
        .agg(
            n_besok=("start", "size"),
            n_fartoy=("mmsi", "nunique"),
            sum_liggetid_timer=("varighet_timer", "sum"),
        )
        .reset_index()
    )
