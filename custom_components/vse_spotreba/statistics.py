"""Import dlhodobych statistik pre HA Energy Dashboard.

Hodinovu spotrebu z VSE vklada ako externe statistiky (statistic_id
'vse_spotreba:...'), ktore je mozne pridat do energetickeho panela ako
zdroj spotreby. Kumulativna suma (sum) nadvazuje na uz ulozene data.
"""
from __future__ import annotations

import datetime as dt
import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_import_hodinove_statistiky(
    hass: HomeAssistant, om: str, hodiny: list[dict]
) -> None:
    """Zapis hodinovu spotrebu do dlhodobych statistik.

    'hodiny' je zoznam {'start': datetime (aware, zarovnane na hodinu),
    'kwh': float} zoradeny vzostupne.
    """
    if not hodiny:
        return

    statistic_id = f"{DOMAIN}:spotreba_{om}"
    metadata: StatisticMetaData = {
        "has_mean": False,
        "has_sum": True,
        "name": f"VSE spotreba {om}",
        "source": DOMAIN,
        "statistic_id": statistic_id,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    }

    # nadviaz na poslednu ulozenu sumu
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum", "start"}
    )
    running = 0.0
    posledny_start: dt.datetime | None = None
    if last.get(statistic_id):
        rec = last[statistic_id][0]
        running = float(rec.get("sum") or 0.0)
        ts = rec.get("start")
        if ts is not None:
            posledny_start = dt_util.utc_from_timestamp(ts) if isinstance(ts, (int, float)) \
                else dt_util.as_utc(ts)

    data: list[StatisticData] = []
    for h in hodiny:
        start: dt.datetime = h["start"]
        if posledny_start is not None and start <= posledny_start:
            continue
        kwh = h.get("kwh") or 0.0
        running += kwh
        data.append(StatisticData(start=start, state=kwh, sum=running))

    if not data:
        return

    _LOGGER.debug("VSE: vkladam %d hodinovych statistik (%s)", len(data), statistic_id)
    async_add_external_statistics(hass, metadata, data)
