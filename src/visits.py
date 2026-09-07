"""
Deteksjon av lokalitetsbesøk fra AIS-posisjonsdata.

Metodikken følger BarentsWatch sin egen definisjon av at et fartøy
"har vært ved en lokalitet": fartøyet må ha vært innenfor en gitt radius
fra lokalitetens midtpunkt med fart under en gitt terskel.

Standardverdiene (400 m, 1 knop) er BarentsWatch sine. Endre dem gjerne,
men dokumenter valget i README - det er en metodisk beslutning, ikke en detalj.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

JORDRADIUS_M = 6_371_000.0

# Standardparametre - dokumenter dem hvis du endrer dem
RADIUS_M = 400.0
MAKS_FART_KNOP = 1.0
MIN_VARIGHET_MIN = 30.0      # kortere opphold regnes som passering, ikke besøk
MAKS_HULL_MIN = 60.0         # AIS-hull kortere enn dette bryter ikke et besøk


def haversine_m(lat1, lon1, lat2, lon2):
    """Avstand i meter mellom punkt(er). Tar skalarer eller numpy-arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2 * JORDRADIUS_M * np.arcsin(np.sqrt(a))


def _naermeste_lokalitet(ais: pd.DataFrame, lokaliteter: pd.DataFrame) -> pd.DataFrame:
    """
    Finn naermeste lokalitet for hver AIS-posisjon.

    Brute force (alle posisjoner x alle lokaliteter). Det holder fint opp til
    noen millioner rader. Blir det tregt, filtrer forst pa bounding box rundt
    lokalitetene, eller bytt til scipy.spatial.cKDTree pa projiserte koordinater.
    """
    pos_lat = ais["lat"].to_numpy()[:, None]
    pos_lon = ais["lon"].to_numpy()[:, None]
    lok_lat = lokaliteter["lat"].to_numpy()[None, :]
    lok_lon = lokaliteter["lon"].to_numpy()[None, :]

    avstand = haversine_m(pos_lat, pos_lon, lok_lat, lok_lon)
    idx = np.argmin(avstand, axis=1)

    ut = ais.copy()
    ut["lokalitet_id"] = lokaliteter["lokalitet_id"].to_numpy()[idx]
    ut["lokalitet_navn"] = lokaliteter["navn"].to_numpy()[idx]
    ut["avstand_m"] = avstand[np.arange(len(ais)), idx]
    return ut


def finn_besok(
    ais: pd.DataFrame,
    lokaliteter: pd.DataFrame,
    radius_m: float = RADIUS_M,
    maks_fart_knop: float = MAKS_FART_KNOP,
    min_varighet_min: float = MIN_VARIGHET_MIN,
    maks_hull_min: float = MAKS_HULL_MIN,
) -> pd.DataFrame:
    """
    Grupper AIS-posisjoner til lokalitetsbesok.

    ais          : kolonner mmsi, tidspunkt (datetime), lat, lon, fart_knop
    lokaliteter  : kolonner lokalitet_id, navn, lat, lon

    Returnerer én rad per besok med start, slutt og varighet.
    """
    paakrevd = {"mmsi", "tidspunkt", "lat", "lon", "fart_knop"}
    if not paakrevd.issubset(ais.columns):
        raise ValueError(f"ais mangler kolonner: {paakrevd - set(ais.columns)}")

    ais = ais.sort_values(["mmsi", "tidspunkt"]).reset_index(drop=True)
    ais = _naermeste_lokalitet(ais, lokaliteter)

    ais["ved_lokalitet"] = (
        (ais["avstand_m"] <= radius_m) & (ais["fart_knop"] < maks_fart_knop)
    )

    # Ny besoksepisode nar fartoy, lokalitet eller status endrer seg,
    # eller nar det er et for stort hull i AIS-dekningen.
    endring = (
        (ais["mmsi"] != ais["mmsi"].shift())
        | (ais["ved_lokalitet"] != ais["ved_lokalitet"].shift())
        | (ais["lokalitet_id"] != ais["lokalitet_id"].shift())
    )
    hull = ais.groupby("mmsi")["tidspunkt"].diff().dt.total_seconds() / 60.0
    endring = endring | (hull > maks_hull_min)
    ais["episode"] = endring.cumsum()

    besok = (
        ais[ais["ved_lokalitet"]]
        .groupby(["episode", "mmsi", "lokalitet_id", "lokalitet_navn"], as_index=False)
        .agg(
            start=("tidspunkt", "min"),
            slutt=("tidspunkt", "max"),
            n_posisjoner=("tidspunkt", "size"),
            median_avstand_m=("avstand_m", "median"),
        )
    )

    besok["varighet_timer"] = (besok["slutt"] - besok["start"]).dt.total_seconds() / 3600.0
    besok = besok[besok["varighet_timer"] * 60 >= min_varighet_min]

    return (
        besok.drop(columns=["episode"])
        .sort_values(["mmsi", "start"])
        .reset_index(drop=True)
    )


def finn_seilaser(besok: pd.DataFrame) -> pd.DataFrame:
    """
    Utled seilaser som mellomrommene mellom to pafolgende besok for samme fartoy.

    NB: et "mellomrom" er ikke nodvendigvis ren seilas. Det kan inneholde
    havneopphold, lossing ved slakteri, verft eller venting. Skal du skille
    disse fra hverandre, ma du legge inn havneposisjoner (BarentsWatch Havner)
    og klassifisere oppholdene. Vaer ærlig om dette i README-en.
    """
    b = besok.sort_values(["mmsi", "start"]).copy()
    b["neste_lokalitet"] = b.groupby("mmsi")["lokalitet_id"].shift(-1)
    b["neste_lokalitet_navn"] = b.groupby("mmsi")["lokalitet_navn"].shift(-1)
    b["neste_start"] = b.groupby("mmsi")["start"].shift(-1)

    seilaser = b.dropna(subset=["neste_start"]).copy()
    seilaser["mellomrom_timer"] = (
        seilaser["neste_start"] - seilaser["slutt"]
    ).dt.total_seconds() / 3600.0

    return seilaser[
        [
            "mmsi",
            "lokalitet_id",
            "lokalitet_navn",
            "slutt",
            "neste_lokalitet",
            "neste_lokalitet_navn",
            "neste_start",
            "mellomrom_timer",
        ]
    ].rename(
        columns={
            "lokalitet_id": "fra_lokalitet",
            "lokalitet_navn": "fra_navn",
            "slutt": "avgang",
            "neste_lokalitet": "til_lokalitet",
            "neste_lokalitet_navn": "til_navn",
            "neste_start": "ankomst",
        }
    ).reset_index(drop=True)
