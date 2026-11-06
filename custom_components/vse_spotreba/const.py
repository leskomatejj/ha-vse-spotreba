"""Konstanty integracie VSE spotreba."""
from __future__ import annotations

import calendar
import datetime as dt
from datetime import timedelta

DOMAIN = "vse_spotreba"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_OP = "op"          # cislo obchodneho partnera
CONF_OM = "om"          # cislo odberneho miesta
CONF_ZU = "zu"          # cislo zmluvneho uctu
CONF_EIC = "eic"        # EIC kod (eicPodKod)
CONF_DNI = "dni"        # (stare) pevny pocet dni - kvoli spatnej kompatibilite
CONF_ROZSAH = "rozsah"  # rozsah historie (kalendarne spravny)

DEFAULT_DNI = 14
DEFAULT_ROZSAH = "30d"
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)

# Hodinovy update stahuje len poslednych RECENT_DNI dni (historia sa nemeni);
# cely 'rozsah' sa stiahne len raz pri backfille do statistik.
RECENT_DNI = 14

# kluc v hass.data: mnozina entry_id, ktore maju vynutit backfill (po zmene rozsahu)
FORCE_BACKFILL = f"{DOMAIN}_force_backfill"

# Moznosti rozsahu historie {kluc: popis pre UI}
ROZSAHY = {
    "7d": "Posledných 7 dní",
    "30d": "Posledných 30 dní",
    "90d": "Posledných 90 dní",
    "tento_mesiac": "Tento mesiac (od 1.)",
    "12m": "Posledných 12 mesiacov",
}


def _minus_mesiace(d: dt.date, n: int) -> dt.date:
    """Odpocita n kalendarnych mesiacov (osetruje rozny pocet dni)."""
    index = d.month - 1 - n
    rok = d.year + index // 12
    mesiac = index % 12 + 1
    den = min(d.day, calendar.monthrange(rok, mesiac)[1])
    return dt.date(rok, mesiac, den)


def datum_od_pre_rozsah(rozsah: str, dnes: dt.date) -> dt.date:
    """Vrati datum 'od' pre dany rozsah (kalendarne spravne)."""
    if rozsah == "tento_mesiac":
        return dnes.replace(day=1)
    if rozsah == "12m":
        return _minus_mesiace(dnes, 12)
    if rozsah.endswith("d"):
        try:
            return dnes - timedelta(days=int(rozsah[:-1]))
        except ValueError:
            pass
    return dnes - timedelta(days=30)
