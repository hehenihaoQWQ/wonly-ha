"""王力智能门锁配置流。"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import WonlyApi, WonlyApiError
from .const import CONF_CLIENT_ID, CONF_CREDENTIAL, CONF_IDENTIFIER, DEFAULT_CLIENT_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


def normalize_identifier(identifier: str) -> str:
    """王力服务端要求手机号带 +86 前缀。"""
    identifier = identifier.strip()
    if "@" in identifier:
        return identifier
    if identifier.startswith("+"):
        return identifier
    if identifier.startswith("86") and len(identifier) == 13:
        return f"+{identifier}"
    return f"+86{identifier}"


class WonlyConfigFlow(ConfigFlow, domain=DOMAIN):
    """处理王力门锁的配置。"""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """用户填写王力 App 的账号密码。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            identifier = normalize_identifier(user_input[CONF_IDENTIFIER])
            credential = user_input[CONF_CREDENTIAL]
            client_id = (user_input.get(CONF_CLIENT_ID) or DEFAULT_CLIENT_ID).strip()

            session = async_get_clientsession(self.hass)
            api = WonlyApi(session, client_id=client_id)
            try:
                await api.async_login(identifier, credential)
            except WonlyApiError as err:
                _LOGGER.warning("王力登录失败: %s", err)
                errors["base"] = "invalid_auth"
            else:
                await self.async_set_unique_id(identifier)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"王力门锁 {identifier}",
                    data={
                        CONF_IDENTIFIER: identifier,
                        CONF_CREDENTIAL: credential,
                        CONF_CLIENT_ID: client_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IDENTIFIER,
                        description={"suggested_value": "+8613930810820"},
                    ): str,
                    vol.Required(CONF_CREDENTIAL): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(
                        CONF_CLIENT_ID,
                        default=DEFAULT_CLIENT_ID,
                        description={"suggested_value": DEFAULT_CLIENT_ID},
                    ): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):  # type: ignore[no-untyped-def]
        """暂不支持选项流。"""
        return None
