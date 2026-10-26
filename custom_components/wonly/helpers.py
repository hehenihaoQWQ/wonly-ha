"""王力门锁实体共用的小工具。"""

from __future__ import annotations

from typing import Any

from .const import DOMAIN, UNLOCK_METHODS


def device_name(lock: dict[str, Any]) -> str:
    """设备展示名。门锁本身没有名字时用分组名。"""
    group = (lock.get("group") or {}).get("name") or ""
    name = lock.get("name") or ""
    if name and group and name != group:
        return f"{group} {name}"
    return name or group or "王力门锁"


def device_info(lock: dict[str, Any], did: str) -> dict[str, Any]:
    """设备信息，lock / sensor / event 三个平台共用。"""
    device = lock.get("device") or {}
    model = device.get("pk") or device.get("product_id") or ""
    return {
        "identifiers": {(DOMAIN, did)},
        "name": device_name(lock),
        "manufacturer": "王力",
        "model": f"智能门锁 {model}".strip(),
    }


def user_type_name(raw: Any) -> str | None:
    """开锁方式 -> 中文（数字编码和字符串编码都支持，两边是同一套中文）。"""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()):
        return UNLOCK_METHODS.get(int(raw), "未知")
    return UNLOCK_METHODS.get(str(raw).upper(), str(raw))
