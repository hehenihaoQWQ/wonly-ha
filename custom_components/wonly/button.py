"""王力门锁的开门按钮（button 实体）。"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WonlyCoordinator
from .helpers import device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """建立开门按钮。"""
    coordinator: WonlyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(WonlyUnlockButton(coordinator, did) for did in coordinator.locks)


class WonlyUnlockButton(CoordinatorEntity[WonlyCoordinator], ButtonEntity):
    """开门按钮：按一下远程开锁。

    这一系列门锁只有远程开锁，没有远程上锁；服务端也不提供「当前是否上锁」的接口，
    状态只能靠事件流推断。所以不提供 lock 实体——前端会把它渲染成一个可开可关的开关，
    容易让人以为还能远程上锁。这里只给一个纯粹的开门按钮，
    已开锁/已上锁的信息由「门锁状态」传感器给出。
    """

    _attr_has_entity_name = True
    _attr_name = "开门"
    _attr_icon = "mdi:door-open"

    def __init__(self, coordinator: WonlyCoordinator, did: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._did = did
        self._attr_unique_id = f"{DOMAIN}_{did}_unlock"

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

    async def async_press(self) -> None:
        """按下按钮：远程开锁。"""
        from . import async_remote_unlock

        await async_remote_unlock(self.hass, self.coordinator, self._did)
