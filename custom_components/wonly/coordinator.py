"""王力门锁数据协调器：REST 拉状态 + WebSocket 推事件。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WonlyApi, WonlyApiError
from .const import (
    CONF_CREDENTIAL,
    CONF_IDENTIFIER,
    DOMAIN,
    LOCKED_EVENTS,
    UNLOCKED_EVENTS,
)
from .helpers import user_type_name

_LOGGER = logging.getLogger(__name__)


def _is_state_event(event: dict[str, Any]) -> bool:
    """是不是开关锁事件。"""
    name = event.get("name")
    return name in LOCKED_EVENTS or name in UNLOCKED_EVENTS


class WonlyCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """把多个门锁的状态汇总成 {did: {...}}。"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: WonlyApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.entry = entry
        self.api = api
        self.identifier: str = entry.data[CONF_IDENTIFIER]
        self.credential: str = entry.data[CONF_CREDENTIAL]
        self.uid: str | None = None
        self.locks: dict[str, dict[str, Any]] = {}
        self._need_diagnose = False

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            await self.api.async_ensure_token(self.identifier, self.credential)
            user = await self.api.async_get_user()
            self.uid = user.get("uid")

            locks: dict[str, dict[str, Any]] = {}
            for group in await self.api.async_get_groups():
                gid = group.get("gid") or group.get("id")
                devices = await self.api.async_get_group_devices(gid)
                for device in devices:
                    if device.get("type") != "LOCK":
                        continue
                    did = device.get("did")
                    if not did:
                        continue
                    events = await self.api.async_get_events(did)
                    state_event = next((e for e in events if _is_state_event(e)), None)
                    # 门锁用户列表只用来把开锁事件里的用户编号翻成别名，
                    # 拉不到不影响门锁本身，失败就降级成空列表。
                    try:
                        users = await self.api.async_get_lock_users(did)
                    except WonlyApiError as err:
                        _LOGGER.warning("拉取门锁 %s 的用户列表失败: %s", did, err)
                        users = []
                        self._need_diagnose = True
                    locks[did] = {
                        "device": device,
                        "group": group,
                        "name": device.get("name") or group.get("name") or did,
                        "state": state_event.get("name") if state_event else None,
                        "event": events[0] if events else None,
                        "state_event": state_event,
                        "users": users,
                    }
            self.locks = locks
            if self._need_diagnose and locks:
                self._need_diagnose = False
                try:
                    await self.api.async_diagnose_users(next(iter(locks)))
                except Exception as err:  # noqa: BLE001 - 诊断用途
                    _LOGGER.warning("诊断失败: %s", err)
            return locks
        except WonlyApiError as err:
            raise UpdateFailed(f"拉取王力门锁数据失败: {err}") from err

    def apply_event(self, did: str, payload: dict[str, Any]) -> None:
        """把 WebSocket 推来的事件合并进当前数据。"""
        lock = self.locks.get(did)
        if lock is None:
            return
        name = payload.get("name")
        event = {
            "name": name,
            "level": payload.get("level"),
            "data": payload.get("data") or {},
            "created_at": payload.get("created_at"),
        }
        lock["event"] = event
        if _is_state_event(event):
            lock["state"] = name
            lock["state_event"] = event
        self.async_set_updated_data(self.locks)

    # ---------- 供实体使用的派生信息 ----------
    @staticmethod
    def unlock_method(lock: dict[str, Any]) -> str | None:
        """最近一次开关锁事件的开锁方式（中文）。"""
        event = lock.get("state_event") or {}
        data = event.get("data") or {}
        lock_user = data.get("lock_user") or {}
        return user_type_name(lock_user.get("type"))

    @staticmethod
    def unlock_user(lock: dict[str, Any]) -> str | None:
        """从事件里的用户编号反查门锁用户别名。

        门锁用户接口返回 {"type": "FINGERPRINT", "number": 3, "alias": ""}，
        事件里的 lock_user.id 对应的就是这个 number。
        """
        event = lock.get("state_event") or {}
        data = event.get("data") or {}
        lock_user = data.get("lock_user") or {}
        user_id = lock_user.get("id")
        if user_id in (None, "", 0, "0"):
            return None

        for user in lock.get("users") or []:
            if str(user.get("number")) != str(user_id):
                continue
            alias = (user.get("alias") or "").strip()
            if alias:
                return alias
            type_name = user_type_name(user.get("type")) or "用户"
            return f"{type_name} {user_id}"
        return f"用户 {user_id}"

    @staticmethod
    def event_time(event: dict[str, Any] | None) -> datetime | None:
        """解析事件时间。"""
        if not event:
            return None
        raw = event.get("created_at")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
