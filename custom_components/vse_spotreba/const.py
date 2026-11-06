"""Konstanty integracie VSE spotreba."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "vse_spotreba"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_OP = "op"          # cislo obchodneho partnera
CONF_OM = "om"          # cislo odberneho miesta
CONF_ZU = "zu"          # cislo zmluvneho uctu
CONF_EIC = "eic"        # EIC kod (eicPodKod)
CONF_DNI = "dni"        # kolko dni dozadu stahovat

DEFAULT_DNI = 14
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
