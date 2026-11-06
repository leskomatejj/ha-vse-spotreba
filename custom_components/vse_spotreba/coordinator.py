"""DataUpdateCoordinator pre VSE spotrebu."""
from __future__ import annotations

import datetime as dt
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import VseAuthError, VseClient, VseError, cislo
from .const import (
    CONF_DNI,
    CONF_EIC,
    CONF_EMAIL,
    CONF_OM,
    CONF_OP,
    CONF_PASSWORD,
    CONF_ZU,
    DEFAULT_DNI,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .statistics import async_import_hodinove_statistiky

_LOGGER = logging.getLogger(__name__)


class VseCoordinator(DataUpdateCoordinator):
    """Pri kazdom cykle sa prihlasi a stiahne spotrebu (data su spatne ~1 den)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        data = entry.data
        self._client = VseClient(data[CONF_EMAIL], data[CONF_PASSWORD])
        self._op = data[CONF_OP]
        self._om = data[CONF_OM]
        self._zu = data[CONF_ZU]
        self._eic = data[CONF_EIC]
        self._dni = entry.options.get(CONF_DNI, data.get(CONF_DNI, DEFAULT_DNI))

    def _fetch(self) -> dict:
        """Synchronna cast - bezi v executor vlakne."""
        token = self._client.login()
        do = dt.date.today() + dt.timedelta(days=1)
        od = do - dt.timedelta(days=self._dni + 1)
        return self._client.spotreba(
            token, self._op, self._om, self._zu, self._eic,
            od.isoformat(), do.isoformat())

    async def _async_update_data(self) -> dict:
        try:
            raw = await self.hass.async_add_executor_job(self._fetch)
        except VseAuthError as err:
            raise UpdateFailed(f"Prihlasenie zlyhalo: {err}") from err
        except VseError as err:
            raise UpdateFailed(str(err)) from err

        dnes = dt.date.today().isoformat()
        dni = sorted(
            ({"datum": r["datum"], "kwh": cislo(r.get("kWh"))}
             for r in raw.get("spotrebyVcaseDetailDen", [])
             if (r.get("kWh") or "").strip() and r["datum"] < dnes),
            key=lambda x: x["datum"])
        posledny = dni[-1] if dni else {"datum": None, "kwh": None}

        hodiny = [
            {"cas": r["cas"], "kwh": cislo(r.get("kWh"))}
            for r in raw.get("spotrebyVcaseDetailHodina", [])
            if r.get("datum") == posledny["datum"] and (r.get("kWh") or "").strip()]

        # import hodinovych dat do Energy Dashboard (dlhodobe statistiky)
        try:
            await self._async_import_statistiky(raw)
        except Exception:  # noqa: BLE001 - statistiky nesmu zhodit senzory
            _LOGGER.exception("VSE: import statistik zlyhal")

        return {
            "posledny_datum": posledny["datum"],
            "posledny_kwh": posledny["kwh"],
            "dni": dni,
            "hodiny": hodiny,
            "spolu_obdobie_kwh": round(sum(d["kwh"] or 0 for d in dni), 2),
        }

    async def _async_import_statistiky(self, raw: dict) -> None:
        """Pozbieraj hodinovu spotrebu za cele okno a posli do statistik."""
        tz = await self.hass.async_add_executor_job(
            dt_util.get_time_zone, self.hass.config.time_zone)
        teraz = dt_util.utcnow()
        hodiny_all = []
        for r in raw.get("spotrebyVcaseDetailHodina", []):
            kwh = cislo(r.get("kWh"))
            if kwh is None or not r.get("datum") or not r.get("cas"):
                continue
            try:
                naive = dt.datetime.strptime(
                    f"{r['datum']} {r['cas']}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            start = naive.replace(tzinfo=tz).astimezone(dt.timezone.utc)
            if start >= teraz:          # preskoc buduce/necele hodiny
                continue
            hodiny_all.append({"start": start, "kwh": kwh})
        hodiny_all.sort(key=lambda x: x["start"])
        await async_import_hodinove_statistiky(self.hass, self._om, hodiny_all)
