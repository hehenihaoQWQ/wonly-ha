"""王力门锁的事件实体：把 WebSocket 推送转成 HA 事件，驱动自动化。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, EVENT_NAMES
from .coordinator import WonlyCoordinator
from .helpers import device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """建立门锁事件实体。"""
    coordinator: WonlyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        WonlyLockEvent(coordinator, did) for did in coordinator.locks
    )


class WonlyLockEvent(CoordinatorEntity[WonlyCoordinator], EventEntity):
    """门锁事件。

    event_type 取协议原始名（UNLOCKED / LOCKED / ...），
    中文含义放在属性「事件」里。
    """

    _attr_has_entity_name = True
    _attr_name = "门锁事件"
    _attr_event_types = sorted(EVENT_NAMES)

    def __init__(self, coordinator: WonlyCoordinator, did: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._did = did
        self._attr_unique_id = f"{DOMAIN}_{did}_event"
        # 记录已上报的事件，避免启动/轮询时重复触发
        self._last_event_key = self._event_key(
            coordinator.locks.get(did, {}).get("event")
        )

    @property
    def _lock(self) -> dict:
        return self.coordinator.locks.get(self._did, {})

    @property
    def device_info(self):
        """设备信息。"""
        return device_info(self._lock, self._did)

    @staticmethod
    def _event_key(event: dict[str, Any] | None) -> str | None:
        """事件唯一标识。"""
        if not event:
            return None
        return f"{event.get('name')}|{event.get('created_at')}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """只在新事件到达时写状态，避免轮询误触发自动化。"""
        event = self._lock.get("event")
        key = self._event_key(event)
        if not key or key == self._last_event_key:
            return

        self._last_event_key = key
        event_type = event.get("name")
        if event_type not in self.event_types:
            return

        data = event.get("data") or {}
        image = data.get("image") or {}
        attributes = {
            "设备ID": self._did,
            "事件": EVENT_NAMES.get(event_type, event_type),
            "事件类型": event.get("level"),
            "开锁方式": self.coordinator.unlock_method(self._lock),
            "开锁用户": self.coordinator.unlock_user(self._lock),
            "事件时间": event.get("created_at"),
            "图片地址": data.get("image_uri") or image.get("uri"),
        }
        # HA 2026.10 起 EventEntity 不再自动往事件总线发事件，
        # 这里自己补一发，老写法（trigger: event）也能继续用。
        self.hass.bus.fire(event_type, attributes)
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
