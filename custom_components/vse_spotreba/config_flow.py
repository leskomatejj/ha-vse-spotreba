"""Config flow (nastavenie cez UI) pre VSE spotrebu."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .api import VseAuthError, VseClient, VseError, op_z_tokenu
from .const import (
    CONF_EIC,
    CONF_EMAIL,
    CONF_OM,
    CONF_OP,
    CONF_PASSWORD,
    CONF_ROZSAH,
    CONF_ZU,
    DEFAULT_ROZSAH,
    DOMAIN,
    ROZSAHY,
)


def _popis_om(om: dict) -> str:
    """Citatelny popis odberneho miesta pre dropdown."""
    a = om.get("adresa", {}) or {}
    adresa = " ".join(
        p for p in [a.get("ulica", ""), a.get("cisloDomu", "")] if p
    ).strip()
    obec = a.get("obec", "")
    typ = om.get("typ", "")
    return f"{om.get('cisloOdbernehoMiesta')} — {adresa}, {obec} ({typ})".strip()


class VseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Dvojkrokove nastavenie: prihlasenie, potom vyber odberneho miesta."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._op: str | None = None
        self._oms: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Krok 1 - prihlasenie + automaticke nacitanie odbernych miest."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = VseClient(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            try:
                token = await self.hass.async_add_executor_job(client.login)
                oms = await self.hass.async_add_executor_job(
                    client.odberne_miesta, token)
            except VseAuthError:
                errors["base"] = "invalid_auth"
            except VseError:
                errors["base"] = "cannot_connect"
            else:
                self._email = user_input[CONF_EMAIL]
                self._password = user_input[CONF_PASSWORD]
                self._op = op_z_tokenu(token) or ""
                self._oms = oms
                return await self.async_step_om()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    async def async_step_om(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Krok 2 - vyber odberneho miesta zo zoznamu (alebo rucne, ak sa nenaslo)."""
        if not self._oms:
            return await self.async_step_om_rucne()

        if user_input is not None:
            om = self._oms[int(user_input["vyber"])]
            return await self._vytvor(om, user_input.get(CONF_ROZSAH, DEFAULT_ROZSAH))

        options = {str(i): _popis_om(om) for i, om in enumerate(self._oms)}
        return self.async_show_form(
            step_id="om",
            data_schema=vol.Schema({
                vol.Required("vyber", default="0"): vol.In(options),
                vol.Optional(CONF_ROZSAH, default=DEFAULT_ROZSAH): vol.In(ROZSAHY),
            }),
        )

    async def async_step_om_rucne(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zaloha - rucne zadanie, ak auto-discovery nic nevratilo."""
        if user_input is not None:
            return await self._vytvor(
                {
                    CONF_OP: user_input[CONF_OP],
                    "cisloObchodnehoPartnera": user_input[CONF_OP],
                    "cisloOdbernehoMiesta": user_input[CONF_OM],
                    "cisloZmluvnehoUctu": user_input[CONF_ZU],
                    "eicPodKod": user_input[CONF_EIC],
                },
                user_input.get(CONF_ROZSAH, DEFAULT_ROZSAH),
            )

        return self.async_show_form(
            step_id="om_rucne",
            data_schema=vol.Schema({
                vol.Required(CONF_OP, default=self._op or ""): str,
                vol.Required(CONF_OM): str,
                vol.Required(CONF_ZU): str,
                vol.Required(CONF_EIC): str,
                vol.Optional(CONF_ROZSAH, default=DEFAULT_ROZSAH): vol.In(ROZSAHY),
            }),
        )

    async def _vytvor(self, om: dict, rozsah: str) -> ConfigFlowResult:
        op = om.get("cisloObchodnehoPartnera") or om.get(CONF_OP) or self._op
        om_cislo = om.get("cisloOdbernehoMiesta") or om.get(CONF_OM)
        await self.async_set_unique_id(f"{op}_{om_cislo}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"VSE {om_cislo}",
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_OP: op,
                CONF_OM: om_cislo,
                CONF_ZU: om.get("cisloZmluvnehoUctu") or om.get(CONF_ZU),
                CONF_EIC: om.get("eicPodKod") or om.get(CONF_EIC),
                CONF_ROZSAH: rozsah,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return VseOptionsFlow()


class VseOptionsFlow(OptionsFlow):
    """Zmena rozsahu historie po instalacii."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_ROZSAH, self.config_entry.data.get(CONF_ROZSAH, DEFAULT_ROZSAH))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_ROZSAH, default=current): vol.In(ROZSAHY),
            }),
        )
