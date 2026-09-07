"""
Last ned fartoysspor for bronnbatene og hent ut slakterianlop.

Kjor etter bygg_besok.py:
    python src/hent_spor.py

BarentsWatch har allerede analysert sporene: trackAnalysis inneholder
slaughterhouseVisits, localityWaypoints, diseaseZoneVisits og
productionAreaVisits. Vi trenger derfor ikke gjore deteksjonen selv.

Et ukesspor har rundt 8000 posisjoner. Vi lagrer derfor bare analysedelen,
ikke punktene - bortsett fra for et lite utvalg (se LAGRE_PUNKTER_FOR), som
beholdes slik at finn_besok() kan valideres mot BarentsWatch sin egen
deteksjon senere.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.barentswatch import BarentsWatchKlient

ROT = Path(__file__).resolve().parents[1]
CACHE = ROT / "data" / "raw" / "spor"
PUNKTER = ROT / "data" / "raw" / "spor_punkter"
UT = ROT / "data" / "processed"

AAR = 2025
UKER = range(1, 53)

# Behold fulle posisjoner for disse ukene, for ett fartoy (det mest aktive).
# Brukes til a validere finn_besok() mot BarentsWatch sin deteksjon.
LAGRE_PUNKTER_FOR = range(30, 35)

PAUSE_SEK = 0.4


def hent_spor(bw: BarentsWatchKlient, mmsi: int, aar: int, uke: int, behold_punkter: bool):
    """Hent ett ukesspor. Lagrer slank versjon i cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fil = CACHE / f"{mmsi}-{aar}-{uke:02d}.json"

    if fil.exists():
        return json.loads(fil.read_text(encoding="utf-8"))

    data = bw.get(f"/bwapi/v1/geodata/fishhealth/vesseltrack/{mmsi}/{aar}/{uke}")
    time.sleep(PAUSE_SEK)

    if behold_punkter:
        PUNKTER.mkdir(parents=True, exist_ok=True)
        (PUNKTER / f"{mmsi}-{aar}-{uke:02d}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    # Slank versjon: alt unntatt selve posisjonene
    slank = {k: v for k, v in data.items() if k != "vesselTracks"}
    slank["n_punkter"] = sum(
        len(s.get("points") or []) for s in (data.get("vesselTracks") or [])
    )
    slank["n_segmenter"] = len(data.get("vesselTracks") or [])

    fil.write_text(json.dumps(slank, ensure_ascii=False), encoding="utf-8")
    return slank


def pakk_ut_anlop(slank: dict, mmsi: int, uke: int) -> list[dict]:
    """Hent slaughterhouseVisits ut av trackAnalysis."""
    analyse = slank.get("trackAnalysis") or {}
    anlop = analyse.get("slaughterhouseVisits") or []

    rader = []
    for a in anlop:
        if not isinstance(a, dict):
            continue
        rad = dict(a)
        rad["mmsi"] = mmsi
        rad["uke"] = uke
        rad["fartoy"] = slank.get("vesselName")
        rader.append(rad)
    return rader


def main():
    besok_fil = UT / "besok_bronnbat.csv"
    if not besok_fil.exists():
        raise SystemExit("Mangler besok_bronnbat.csv. Kjor bygg_besok.py forst.")

    besok = pd.read_csv(besok_fil)
    bater = (
        besok.groupby(["mmsi", "fartoy"]).size().sort_values(ascending=False).reset_index()
    )

    n_kall = len(bater) * len(UKER)
    print(f"{len(bater)} bronnbater x {len(UKER)} uker = {n_kall} kall")
    print(f"Anslatt tid: {n_kall * (PAUSE_SEK + 0.6) / 60:.0f} minutter\n")
    print("Cachen gjor at du trygt kan avbryte og starte igjen.\n")

    bw = BarentsWatchKlient()
    mest_aktive = int(bater.iloc[0]["mmsi"])

    alle_anlop = []
    feil = 0

    for i, rad in bater.iterrows():
        mmsi = int(rad["mmsi"])
        navn = rad["fartoy"]
        anlop_bat = 0

        for uke in UKER:
            behold = mmsi == mest_aktive and uke in LAGRE_PUNKTER_FOR
            try:
                slank = hent_spor(bw, mmsi, AAR, uke, behold)
            except Exception:
                feil += 1
                continue

            rader = pakk_ut_anlop(slank, mmsi, uke)
            alle_anlop.extend(rader)
            anlop_bat += len(rader)

        print(f"  [{i + 1:2d}/{len(bater)}] {str(navn)[:22]:24s} {anlop_bat:4d} slakterianlop")

    if not alle_anlop:
        print(f"\nIngen slakterianlop funnet ({feil} feilede kall).")
        print("Sjekk om slaughterhouseVisits faktisk er utfylt i sporene.")
        return

    df = pd.json_normalize(alle_anlop)
    df.to_csv(UT / "slakterianlop_raa.csv", index=False)

    print(f"\n{'=' * 62}")
    print(f"{len(df)} slakterianlop, {feil} feilede kall")
    print(f"Skrevet til data/processed/slakterianlop_raa.csv")

    print("\nKOLONNER:")
    for kol in df.columns:
        eks = df[kol].dropna()
        vis = eks.iloc[0] if len(eks) else "(alle tomme)"
        print(f"  {kol:34s} {str(vis)[:44]}")

    print("\nFORSTE 3 RADER:")
    print(df.head(3).to_string())


if __name__ == "__main__":
    main()
