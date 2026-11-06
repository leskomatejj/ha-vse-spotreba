"""Klient pre portal VSE (www.vse.sk).

Prihlasenie cez Azure AD B2C (OAuth2 + PKCE, email+heslo) a stiahnutie
priebehovej spotreby elektriny z inteligentneho merača.

Modul je nezavisly od Home Assistantu a pouziva len standardnu kniznicu
(ziadne externe balicky). Je synchronny - HA ho vola cez executor.
"""
from __future__ import annotations

import base64
import binascii
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
LOGIN_URL = "https://www.vse.sk/identity-api/login"
CODEUSER_URL = "https://www.vse.sk/identity-api/codeUser"
SPOTREBA_URL = "https://www.vse.sk/ods-api/op/om/spotrebaHistoriaPriebehove"
OM_URL = "https://www.vse.sk/ods-api/op/om"
EXCHANGE = "LocalAccountSigninEmailExchange"
TIMEOUT = 30


class VseError(Exception):
    """Vseobecna chyba integracie VSE."""


class VseAuthError(VseError):
    """Chyba prihlasenia (zle udaje, zmena login flow)."""


def _settings(html: str) -> dict:
    m = re.search(r"var SETTINGS\s*=\s*(\{.*?\});", html, re.S)
    if not m:
        raise VseAuthError("Nenajdene SETTINGS na B2C stranke.")
    return json.loads(m.group(1))


def op_z_tokenu(token: str) -> str | None:
    """Vytiahne cislo obchodneho partnera (ops) z JWT tokenu."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("ops")
    except (IndexError, ValueError, binascii.Error, json.JSONDecodeError):
        return None


class VseClient:
    """Synchronny klient: prihlasenie + stiahnutie spotreby."""

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    # --- nizkourovnove HTTP ---------------------------------------------
    def _get(self, url: str, headers: dict | None = None) -> tuple[str, str]:
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        with self._opener.open(req, timeout=TIMEOUT) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")

    def _post(self, url: str, body, headers: dict, as_json: bool = False) -> str:
        data = (json.dumps(body).encode() if as_json
                else urllib.parse.urlencode(body).encode())
        ct = "application/json" if as_json else "application/x-www-form-urlencoded"
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"User-Agent": UA, "Content-Type": ct, **(headers or {})})
        with self._opener.open(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")

    # --- prihlasenie -----------------------------------------------------
    def login(self) -> str:
        """Vykona cely B2C login a vrati platny Bearer token."""
        try:
            url, html = self._get(LOGIN_URL)
            if "b2clogin.com" not in url:
                raise VseAuthError("Login nepresmeroval na B2C.")
            cfg = _settings(html)
            csrf, tx = cfg["csrf"], cfg["transId"]
            policy, tenant = cfg["hosts"]["policy"], cfg["hosts"]["tenant"]
            pu = urllib.parse.urlparse(url)
            base = f"{pu.scheme}://{pu.netloc}{tenant}"

            # vyber lokalneho uctu (email), ak je prva stranka vyber providera
            if cfg.get("api") == "ClaimsProviderSelection":
                q = urllib.parse.urlencode(
                    {"accountId": EXCHANGE, "csrf_token": csrf, "tx": tx, "p": policy})
                _, html2 = self._get(
                    f"{base}/api/ClaimsProviderSelection/selected?{q}",
                    headers={"Referer": url})
                c2 = _settings(html2)
                csrf, tx = c2["csrf"], c2["transId"]

            q = urllib.parse.urlencode({"tx": tx, "p": policy})
            sa = self._post(
                f"{base}/SelfAsserted?{q}",
                {"request_type": "RESPONSE", "signInName": self._email,
                 "password": self._password},
                headers={"X-CSRF-TOKEN": csrf, "X-Requested-With": "XMLHttpRequest"})
            if json.loads(sa).get("status") != "200":
                raise VseAuthError("Prihlasenie zlyhalo (nespravne udaje).")

            q = urllib.parse.urlencode(
                {"rememberMe": "false", "csrf_token": csrf, "tx": tx, "p": policy})
            final_url, _ = self._get(f"{base}/api/CombinedSigninAndSignup/confirmed?{q}")
            if "code=" not in final_url:
                raise VseAuthError("Nedostal som autorizacny code.")
            search = "?" + final_url.split("?", 1)[1]

            _, body = self._get(CODEUSER_URL + search + "&platforma=WEB")
            token = json.loads(body).get("token")
            if not token:
                raise VseAuthError("codeUser nevratil token.")
            return token
        except urllib.error.URLError as err:
            raise VseError(f"Sietova chyba pri prihlaseni: {err}") from err

    # --- data ------------------------------------------------------------
    def odberne_miesta(self, token: str) -> list[dict]:
        """Vrati zoznam odbernych miest (OP/OM/ZU/EIC/adresa/typ) pre uzivatela."""
        op = op_z_tokenu(token)
        try:
            body = self._post(
                OM_URL, {"cislaOP": [op] if op else [], "aktualne": "0"},
                headers={"Authorization": f"Bearer {token}", "Accept-Language": "sk"},
                as_json=True)
            data = json.loads(body)
            return data if isinstance(data, list) else []
        except urllib.error.HTTPError as err:
            if err.code == 401:
                raise VseAuthError("Token neplatny/vyprsal.") from err
            raise VseError(f"Chyba ods-api (op/om): HTTP {err.code}") from err
        except urllib.error.URLError as err:
            raise VseError(f"Sietova chyba (op/om): {err}") from err

    def spotreba(self, token: str, op: str, om: str, zu: str, eic: str,
                 datum_od: str, datum_do: str) -> dict:
        """Stiahne priebehovu spotrebu. Datumy vo formate YYYY-MM-DD."""
        try:
            body = self._post(
                SPOTREBA_URL,
                {"cisloObchodnehoPartnera": op, "cisloOdbernehoMiesta": om,
                 "cisloZmluvnehoUctu": zu, "eicPodKod": eic,
                 "datumOd": f"{datum_od}T00:00:00.000Z",
                 "datumDo": f"{datum_do}T00:00:00.000Z"},
                headers={"Authorization": f"Bearer {token}", "Accept-Language": "sk"},
                as_json=True)
            return json.loads(body)
        except urllib.error.HTTPError as err:
            if err.code == 401:
                raise VseAuthError("Token neplatny/vyprsal.") from err
            raise VseError(f"Chyba ods-api: HTTP {err.code}") from err
        except urllib.error.URLError as err:
            raise VseError(f"Sietova chyba pri stahovani dat: {err}") from err


def cislo(s: str | None) -> float | None:
    """'0,13' -> 0.13 ; '' -> None (VSE pouziva desatinnu ciarku)."""
    s = (s or "").strip()
    return round(float(s.replace(",", ".")), 3) if s else None
