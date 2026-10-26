"""王力门锁的 lock 实体。"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOCKED_EVENTS, UNLOCKED_EVENTS
from .coordinator import WonlyCoordinator
from .helpers import device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """建立门锁实体。"""
    coordinator: WonlyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        WonlyLock(coordinator, did) for did in coordinator.locks
    )


class WonlyLock(CoordinatorEntity[WonlyCoordinator], LockEntity):
    """王力智能门锁。

    必须继承 CoordinatorEntity：不继承的话它走 HA 默认的 30 秒实体轮询，
    状态会有几十秒延迟（传感器/事件实体是协调器推送，即时更新）。
    """

    _attr_has_entity_name = True
    _attr_name = "门锁"
    # 这系列门锁没有独立的「打开」动作（开锁就是开门），所以不要声明
    # LockEntityFeature.OPEN —— 声明了 HA 会多出一个「打开」按钮，
    # 点了会走 lock.open -> 实体没实现 open() -> NotImplementedError。
    # lock.unlock 本身不需要 feature 标志，所有 lock 实体都支持。
    _attr_supported_features = LockEntityFeature(0)

    def __init__(self, coordinator: WonlyCoordinator, did: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._did = did
        self._attr_unique_id = f"{DOMAIN}_{did}"

    @property
    def _lock(self) -> dict:
        return self.coordinator.locks.get(self._did, {})

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

    async def async_unlock(self, **kwargs: Any) -> None:
        """远程开锁。"""
        from . import async_remote_unlock

        await async_remote_unlock(self.hass, self.coordinator, self._did)

    async def async_lock(self) -> None:
        """王力这一系列不支持远程上锁。"""
        raise HomeAssistantError("该门锁不支持远程上锁，请在门内侧上锁")

    async def async_open(self, **kwargs: Any) -> None:
        """没有独立的「打开」动作。

        基础类的 open() 会直接抛 NotImplementedError，HA 前端只显示
        "Unknown error"，这里换成能看懂的提示。
        """
        raise HomeAssistantError("该门锁没有单独的「打开」动作，请用「开锁」")
