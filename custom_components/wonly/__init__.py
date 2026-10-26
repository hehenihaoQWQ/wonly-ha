"""王力智能门锁 (go.kiwik.cn) 集成。

登录换 token -> 拉门锁状态 -> WebSocket 收事件 -> 暴露 lock/sensor/event 实体。
"""

from __future__ import annotations

import asyncio
import json
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WonlyApi, WonlyApiError
from .const import (
    CONF_CLIENT_ID,
    CONF_CREDENTIAL,
    CONF_IDENTIFIER,
    CONF_SECURE_PASSWORD,
    DEFAULT_CLIENT_ID,
    DOMAIN_DATA,
    PLATFORMS,
)
from .coordinator import WonlyCoordinator
from .protocol import build_unlock_payload
from .ws import WonlyConnection

_LOGGER = logging.getLogger(__name__)

RECONNECT_MAX_DELAY = 60


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """配置一个王力账号。"""
    # 用 HA 共享的 aiohttp session，不要自己 close（HA 会在停机时统一收）
    session = async_get_clientsession(hass)
    api = WonlyApi(
        session,
        client_id=entry.data.get(CONF_CLIENT_ID) or DEFAULT_CLIENT_ID,
    )
    coordinator = WonlyCoordinator(hass, entry, api)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001 - 交由 HA 稍后重试
        _LOGGER.error("王力门锁初始化失败: %s", err)
        raise ConfigEntryNotReady(f"王力门锁初始化失败: {err}") from err

    hass.data.setdefault(DOMAIN_DATA, {})
    hass.data[DOMAIN_DATA][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "connection": None,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    # 任务绑定在配置项上，卸载配置时自动取消
    entry.async_create_background_task(
        hass, _async_ws_loop(hass, entry, api, coordinator), "wonly_ws"
    )
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """配置变更后重载。"""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置项。"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN_DATA, {}).pop(entry.entry_id, None)
    if data:
        connection = data.get("connection")
        if connection is not None:
            await connection.async_close()
    if not hass.data.get(DOMAIN_DATA):
        hass.data.pop(DOMAIN_DATA, None)
    return unload_ok


async def async_remote_unlock(
    hass: HomeAssistant, coordinator: WonlyCoordinator, did: str
) -> None:
    """远程开锁：换 secureToken -> 下发 Ctrl -> 等应答。"""
    entry = coordinator.entry

    data = hass.data.get(DOMAIN_DATA, {}).get(entry.entry_id)
    if not data:
        raise HomeAssistantError("王力门锁集成未初始化")

    api: WonlyApi = data["api"]
    connection: WonlyConnection | None = data.get("connection")
    if connection is None or not connection.connected:
        raise HomeAssistantError("王力门锁实时连接未就绪，请稍后再试")

    uid = coordinator.uid
    if not uid:
        await coordinator.async_refresh()
        uid = coordinator.uid
    if not uid:
        raise HomeAssistantError("未获取到王力账号信息")

    # 指令内容按门锁的协议号（pk）决定，见 protocol.build_unlock_payload
    device = (coordinator.locks.get(did) or {}).get("device") or {}
    payload = build_unlock_payload(uid, str(device.get("pk") or ""))

    # 换开锁凭证：填了「开锁密码」就用它（secure_password），
    # 否则退回账号登录密码（password）。
    secure_password = (entry.data.get(CONF_SECURE_PASSWORD) or "").strip()
    if secure_password:
        auth_type = "secure_password"
        credential = secure_password
    else:
        auth_type = "password"
        credential = entry.data[CONF_CREDENTIAL]

    try:
        secure_token = await api.async_create_secure_token(
            uid, credential, auth_type
        )
    except WonlyApiError as err:
        raise HomeAssistantError(f"获取远程开锁凭证失败: {err}") from err

    try:
        response = await connection.async_ctrl(did, secure_token, payload)
    except WonlyApiError as err:
        raise HomeAssistantError(f"远程开锁失败: {err}") from err

    header = response.get("header") or {}
    # 应答内容先用 WARNING 打出来，方便在 HA 的系统日志里核对服务端到底回了什么
    _LOGGER.warning(
        "王力开锁应答 %s: %s",
        header.get("name"),
        json.dumps(response.get("payload") or {}, ensure_ascii=False)[:500],
    )
    if header.get("name") == "ErrorResponse":
        payload_data = response.get("payload") or {}
        message = (
            payload_data.get("message")
            or payload_data.get("error_description")
            or payload_data.get("errorCode")
            or "服务端返回错误"
        )
        raise HomeAssistantError(f"远程开锁失败: {message}")

    _LOGGER.info("王力门锁 %s 远程开锁指令执行成功", did)
    await coordinator.async_request_refresh()


async def _async_ws_loop(
    hass: HomeAssistant, entry: ConfigEntry, api: WonlyApi, coordinator: WonlyCoordinator
) -> None:
    """保持 WebSocket 长连接，接收门锁事件。"""
    retry = 0
    while True:
        connection: WonlyConnection | None = None
        try:
            await api.async_ensure_token(
                entry.data[CONF_IDENTIFIER], entry.data[CONF_CREDENTIAL]
            )
            connection = WonlyConnection(api, coordinator.apply_event)
            await connection.async_connect()
            data = hass.data.get(DOMAIN_DATA, {}).get(entry.entry_id)
            if data is not None:
                data["connection"] = connection
            retry = 0
            # 等到连接断开
            await connection.async_wait_closed()
        except asyncio.CancelledError:
            raise
        except WonlyApiError as err:
            _LOGGER.error("王力门锁 WebSocket 断开: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("王力门锁 WebSocket 异常: %s", err)
        finally:
            data = hass.data.get(DOMAIN_DATA, {}).get(entry.entry_id)
            if data is not None and data.get("connection") is connection:
                data["connection"] = None
            if connection is not None:
                await connection.async_close()

        if entry.entry_id not in hass.data.get(DOMAIN_DATA, {}):
            return
        retry += 1
        await asyncio.sleep(min(RECONNECT_MAX_DELAY, 5 * retry))
