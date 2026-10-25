"""王力门锁的传感器实体。"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, EVENT_NAMES
from .coordinator import WonlyCoordinator
from .helpers import device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """建立门锁传感器。"""
    coordinator: WonlyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []
    for did in coordinator.locks:
        entities.append(WonlyStatusSensor(coordinator, did))
        entities.append(WonlyEventTimeSensor(coordinator, did))
    async_add_entities(entities)


class _WonlySensorBase(CoordinatorEntity[WonlyCoordinator]):
    """门锁传感器基类。"""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WonlyCoordinator, did: str) -> None:
        super().__init__(coordinator)
        self._did = did

    @property
    def _lock(self) -> dict:
        return self.coordinator.locks.get(self._did, {})

    @property
    def available(self) -> bool:
        """设备在线即可用。"""
        return bool(self._lock)

    @property
    def device_info(self):
        """设备信息。"""
        return device_info(self._lock, self._did)


class WonlyStatusSensor(_WonlySensorBase):
    """门锁当前状态。"""

    _attr_name = "门锁状态"

    def __init__(self, coordinator: WonlyCoordinator, did: str) -> None:
        super().__init__(coordinator, did)
        self._attr_unique_id = f"{DOMAIN}_{did}_status"

    @property
    def native_value(self) -> str | None:
        """当前状态中文名。"""
        state = self._lock.get("state")
        if not state:
            return None
        return EVENT_NAMES.get(state, state)

    @property
    def extra_state_attributes(self) -> dict:
        """开锁方式、用户、图片等。"""
        state_event = self._lock.get("state_event") or {}
        data = state_event.get("data") or {}
        image = data.get("image") or {}
        return {
            "设备ID": self._did,
            "事件": state_event.get("name"),
            "事件类型": state_event.get("level"),
            "开锁方式": self.coordinator.unlock_method(self._lock),
            "开锁用户": self.coordinator.unlock_user(self._lock),
            "事件时间": state_event.get("created_at"),
            "图片地址": data.get("image_uri") or image.get("uri"),
        }


class WonlyEventTimeSensor(_WonlySensorBase):
    """最近一次事件的时间。"""

    _attr_name = "最近事件时间"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: WonlyCoordinator, did: str) -> None:
        super().__init__(coordinator, did)
        self._attr_unique_id = f"{DOMAIN}_{did}_event_time"

    @property
    def native_value(self) -> datetime | None:
        """事件时间。"""
        return self.coordinator.event_time(self._lock.get("event"))

    @property
    def extra_state_attributes(self) -> dict:
        """附加属性。"""
        event = self._lock.get("event") or {}
        return {
            "事件": event.get("name"),
            "事件中文": EVENT_NAMES.get(event.get("name"), event.get("name")),
        }
