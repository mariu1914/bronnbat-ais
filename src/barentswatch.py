"""
Klient mot BarentsWatch-APIene.

"""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://id.barentswatch.no/connect/token"
BASE_URL = "https://www.barentswatch.no"
SCOPE = "api"


class BarentsWatchKlient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        self.client_id = client_id or os.getenv("BARENTSWATCH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("BARENTSWATCH_CLIENT_SECRET")

        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "Mangler BARENTSWATCH_CLIENT_ID / BARENTSWATCH_CLIENT_SECRET.\n"
                "Kopier .env.example til .env og fyll inn verdiene fra "
                "barentswatch.no > Min side > API-tilgang."
            )

        self._token: str | None = None
        self._utloper: float = 0.0

    def _hent_token(self) -> str:
        """Hent nytt access token hvis det gamle er utlopt (med 60 sek margin)."""
        if self._token and time.time() < self._utloper - 60:
            return self._token

        svar = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": SCOPE,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )

        if svar.status_code != 200:
            raise RuntimeError(
                f"Fikk ikke token ({svar.status_code}). Sjekk client_id og secret.\n"
                f"Svar: {svar.text[:400]}"
            )

        data = svar.json()
        self._token = data["access_token"]
        self._utloper = time.time() + float(data.get("expires_in", 3600))
        return self._token

    def get(self, sti: str, **params: Any) -> Any:
        """
        GET mot et BarentsWatch-endepunkt.

        sti: full sti som begynner med /, f.eks.
             "/bwapi/v1/geodata/fishhealth/localities/2025/10"
        """
        url = sti if sti.startswith("http") else f"{BASE_URL}{sti}"

        svar = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {self._hent_token()}",
                "Accept": "application/json",
            },
            params=params or None,
            timeout=60,
        )

        if svar.status_code == 404:
            raise RuntimeError(
                f"404 pa {url}\n"
                "Stien finnes trolig ikke. Sjekk Swagger-dokumentasjonen "
                "for riktig endepunkt."
            )
        svar.raise_for_status()
        return svar.json()


def test_tilkobling() -> None:
    """Kjor `python src/barentswatch.py` for a sjekke at nokkelen virker."""
    bw = BarentsWatchKlient()
    token = bw._hent_token()
    print("Autentisering OK.")
    print(f"Token mottatt ({len(token)} tegn), utloper om "
          f"{int(bw._utloper - time.time())} sekunder.")
    print("\nNeste steg: apne Swagger, finn endepunktet for lokaliteter og")
    print("fartoystrafikk, og prov et kall med bw.get(...)")


if __name__ == "__main__":
    test_tilkobling()
