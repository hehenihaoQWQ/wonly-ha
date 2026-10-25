"""王力门锁的 lock 实体。"""

from __future__ import annotations

import logging

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOCKED_EVENTS, UNLOCKED_EVENTS
from .coordinator import WonlyCoordinator
from .helpers import device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """建立门锁实体。"""
    coordinator: WonlyCoordinator = hass.data["wonly"][entry.entry_id]["coordinator"]
    async_add_entities(
        WonlyLock(coordinator, did) for did in coordinator.locks
    )


class WonlyLock(LockEntity):
    """王力智能门锁。"""

    _attr_has_entity_name = True
    _attr_name = "门锁"
    # 该系列只支持远程开锁，上锁需在门内侧操作
    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(self, coordinator: WonlyCoordinator, did: str) -> None:
        self._coordinator = coordinator
        self._did = did
        self._attr_unique_id = f"{DOMAIN}_{did}"

    @property
    def _lock(self) -> dict:
        return self._coordinator.locks.get(self._did, {})

    @property
    def available(self) -> bool:
        """设备在线即可用。"""
        return bool(self._lock)

    @property
    def is_locked(self) -> bool | None:
        """当前是否上锁。"""
        state = self._lock.get("state")
        if state in LOCKED_EVENTS:
            return True
        if state in UNLOCKED_EVENTS:
            return False
        return None

    @property
    def device_info(self):
        """设备信息。"""
        return device_info(self._lock, self._did)

    @property
    def extra_state_attributes(self) -> dict:
        """附加属性。"""
        event = self._lock.get("event") or {}
        return {
            "设备ID": self._did,
            "最近事件": event.get("name"),
            "事件时间": event.get("created_at"),
        }

    async def async_unlock(self) -> None:
        """远程开锁。"""
        from . import async_remote_unlock

        await async_remote_unlock(self.hass, self._coordinator, self._did)

    async def async_lock(self) -> None:
        """王力这一系列不支持远程上锁。"""
        raise HomeAssistantError("该门锁不支持远程上锁，请在门内侧上锁")
