"""王力智能门锁 (go.kiwik.cn) 常量。

王力 H5 是 KiwiOT(优智云家) 的白标：后端与 h5.kiwik.cn 完全一致，
只有前端、realm 和 clientId 不同，所以这里直接写死王力的那一份。
"""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "wonly"
DOMAIN_DATA: Final = DOMAIN

CONF_IDENTIFIER: Final = "identifier"
CONF_CREDENTIAL: Final = "credential"
CONF_CLIENT_ID: Final = "client_id"

# 王力 App 的 clientId（白标标识，非密钥）
DEFAULT_CLIENT_ID: Final = "980tSgPSaW8WQ3HDKdyiyJKQymGqxMzl"

BASE_URL: Final = "https://go.kiwik.cn"
WS_URL: Final = "wss://wsapi.kiwiot.com/"

PLATFORMS: Final = [Platform.LOCK, Platform.SENSOR, Platform.EVENT]

# 设备指令码（与王力 App 内嵌的 KiwiOT 协议一致）
CMD_DOORPW: Final = 2063  # 门密码开锁
CMD_STATUS: Final = 2065  # 查询状态

# 事件名 -> 展示用中文
EVENT_NAMES: Final = {
    "UNLOCKED": "已开锁",
    "LOCKED": "已上锁",
    "DOOR_LOCKED": "门上锁",
    "DOOR_UNLOCKED": "门未上锁",
    "EMERGENCY_UNLOCK": "紧急开锁",
    "LOCK_INDOOR_BUTTON_UNLOCK": "室内按钮开锁",
    "LOCK_INDOOR_LEVER_UNLOCK": "室内把手开锁",
    "LOCK_TIMED_LOCK": "定时上锁",
    "DOOR_LOCK_UNLOCKED_KNOB": "旋钮开锁",
    "LOCKED_BY_LEVER": "把手锁定",
    "ARMED_DOOR_LOCK_UNLOCKED": "布防状态门未锁",
    "ACTIVE_MONITOR": "拍照监控",
    "REMOTE_UNLOCK": "远程开锁",
}

# 事件名 -> 上锁状态
LOCKED_EVENTS: Final = {
    "LOCKED",
    "DOOR_LOCKED",
    "LOCK_TIMED_LOCK",
    "LOCKED_BY_LEVER",
}
UNLOCKED_EVENTS: Final = {
    "UNLOCKED",
    "DOOR_UNLOCKED",
    "EMERGENCY_UNLOCK",
    "LOCK_INDOOR_BUTTON_UNLOCK",
    "LOCK_INDOOR_LEVER_UNLOCK",
    "DOOR_LOCK_UNLOCKED_KNOB",
}

# 开锁方式 -> 中文
UNLOCK_METHODS: Final = {
    "PHONE": "手机",
    "PASSWORD": "密码",
    "FINGERPRINT": "指纹",
    "FACE": "人脸",
    "CARD": "门卡",
    "KEY": "钥匙",
    "KNOB": "旋钮",
    "INDOOR_BUTTON": "室内按钮",
    "INDOOR_LEVER": "室内把手",
    "APP": "App",
}

# 事件里 lock_user.type 的数字编码 -> 中文（与王力 App 一致）
USER_TYPE_MAP: Final = {
    0: "门内",
    1: "指纹",
    2: "密码",
    3: "门卡",
    5: "远程",
    6: "人脸",
    7: "掌纹",
    9: "临时密码",
}
