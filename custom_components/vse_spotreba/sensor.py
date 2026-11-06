"""Senzory VSE spotreby."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_OM, DOMAIN
from .coordinator import VseCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Pridaj senzory z config entry."""
    coordinator: VseCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        VseDennaSpotrebaSensor(coordinator, entry),
        VseObdobieSpotrebaSensor(coordinator, entry),
    ])


class _VseBase(CoordinatorEntity[VseCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: VseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        om = entry.data[CONF_OM]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"VSE odberné miesto {om}",
            manufacturer="Východoslovenská energetika",
            model="Inteligentný merač",
        )


class VseDennaSpotrebaSensor(_VseBase):
    """Spotreba za posledny kompletny den [kWh]."""

    _attr_translation_key = "denna_spotreba"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: VseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_denna"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("posledny_kwh")

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {
            "datum": d.get("posledny_datum"),
            "dni": d.get("dni"),
            "hodiny": d.get("hodiny"),
        }


class VseObdobieSpotrebaSensor(_VseBase):
    """Suhrnna spotreba za stahovane obdobie [kWh]."""

    _attr_translation_key = "obdobie_spotreba"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:chart-bar"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: VseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_obdobie"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("spolu_obdobie_kwh")
