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
    CONF_ROZSAH,
    CONF_ZU,
    DEFAULT_DNI,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FORCE_BACKFILL,
    RECENT_DNI,
    datum_od_pre_rozsah,
)
from .statistics import async_import_hodinove_statistiky, async_posledny_start

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
        self._backfill_hotovy = False   # backfill celeho rozsahu spravime raz

    def _rozsah(self) -> str | None:
        """Aktualne nastaveny rozsah (options maju prednost pred data)."""
        return self.entry.options.get(
            CONF_ROZSAH, self.entry.data.get(CONF_ROZSAH))

    def _datum_od(self, dnes: dt.date) -> dt.date:
        """Vypocita datum 'od' podla rozsahu; fallback na stare 'dni'."""
        rozsah = self._rozsah()
        if rozsah:
            return datum_od_pre_rozsah(rozsah, dnes)
        dni = self.entry.options.get(
            CONF_DNI, self.entry.data.get(CONF_DNI, DEFAULT_DNI))
        return dnes - dt.timedelta(days=dni)

    def _fetch(self, od: dt.date, do: dt.date) -> dict:
        """Synchronna cast - bezi v executor vlakne."""
        token = self._client.login()
        return self._client.spotreba(
            token, self._op, self._om, self._zu, self._eic,
            od.isoformat(), do.isoformat())

    async def _async_update_data(self) -> dict:
        dnes = dt.date.today()
        do = dnes + dt.timedelta(days=1)

        # Rozhodni, ci treba jednorazovy backfill celeho rozsahu, alebo staci
        # lacny update poslednych dni (historia sa uz nemeni).
        if not self._backfill_hotovy:
            # vynuteny backfill po zmene rozsahu?
            vynutene = self.hass.data.get(FORCE_BACKFILL, set())
            force = self.entry.entry_id in vynutene
            vynutene.discard(self.entry.entry_id)
            posledny = await async_posledny_start(self.hass, self._om)
            treba_backfill = (
                force
                or posledny is None
                or posledny.date() < dnes - dt.timedelta(days=2))
            if treba_backfill:
                od = self._datum_od(dnes) - dt.timedelta(days=1)   # cely rozsah
            else:
                od = dnes - dt.timedelta(days=RECENT_DNI)           # uz mame historiu
            self._backfill_hotovy = True
        else:
            od = dnes - dt.timedelta(days=RECENT_DNI)               # bezny hodinovy update

        try:
            raw = await self.hass.async_add_executor_job(self._fetch, od, do)
        except VseAuthError as err:
            raise UpdateFailed(f"Prihlasenie zlyhalo: {err}") from err
        except VseError as err:
            raise UpdateFailed(str(err)) from err

        # atribut 'dni' drzime kratky (poslednych RECENT_DNI dni) nezavisle od
        # toho, ci slo o backfill - dlha historia je v Energy Dashboarde
        dnes_s = dnes.isoformat()
        hranica_s = (dnes - dt.timedelta(days=RECENT_DNI)).isoformat()
        dni = sorted(
            ({"datum": r["datum"], "kwh": cislo(r.get("kWh"))}
             for r in raw.get("spotrebyVcaseDetailDen", [])
             if (r.get("kWh") or "").strip() and hranica_s <= r["datum"] < dnes_s),
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
        # len UPLNE dni (datum < dnesny lokalny datum) - dnesok este nema finalne
        # data a statistiky su append-only, nulove hodiny by ostali natrvalo
        dnes_local = dt_util.now().date().isoformat()
        hodiny_all = []
        for r in raw.get("spotrebyVcaseDetailHodina", []):
            kwh = cislo(r.get("kWh"))
            if kwh is None or not r.get("datum") or not r.get("cas"):
                continue
            if r["datum"] >= dnes_local:     # preskoc dnesok (necely den)
                continue
            try:
                naive = dt.datetime.strptime(
                    f"{r['datum']} {r['cas']}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            start = naive.replace(tzinfo=tz).astimezone(dt.timezone.utc)
            hodiny_all.append({"start": start, "kwh": kwh})
        hodiny_all.sort(key=lambda x: x["start"])
        await async_import_hodinove_statistiky(self.hass, self._om, hodiny_all)
