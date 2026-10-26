"""王力(KiwiOT) 设备指令打包。

协议细节来自王力 App 的前端代码（App 和社区版 kiwiot_ws 是同一套 KiwiOT 后端）：

    XD(cmd, data) = base64(大端 cmd 两字节 ++ data)

**字节序是大端的**：App 用 ``DataView.setInt16(0, cmd)`` 且没有传 littleEndian，
DataView 默认按大端写；它自己的解析函数 ``ET()`` 同样按大端读，写读两侧一致。
（这一点如果按小端理解，服务端会 ACK 但门锁不动作，表现为「点了没反应」。）

远程开锁按门锁的 ``pk`` 分两种走法（王力 App 的 startUnlock）：

- ``pk`` 以 ``1002`` 开头（王力自有协议的门锁）：
  用 CMDCACHE 套一层 RMUNLK，指令里必须带 uid：

      [BE16 后续长度][BE32 有效期秒][BE16 命令块长][BE16 RMUNLK][len+2,标志,len,uid...]

- 其它 pk（老协议门锁）：直接 ``DOORPW + [1]``。
"""

from __future__ import annotations

import base64

# 设备指令码
CMD_DOORPW = 2063  # 门密码开锁
CMD_RMUNLK = 5132  # 远程开锁
CMD_CMDCACHE = 5638  # 缓存命令（给 1002 协议的门锁用）
CMD_SELFVIEW = 5134  # 拍照监控（也是最可靠的唤醒方式）

# 远程开锁指令在服务端缓存的有效期（秒）。
# 王力 App 远程开锁用 60 秒（pk 为 100000001601 的老协议用 10 秒）。
UNLOCK_TTL_SECONDS = 60


def _be16(value: int) -> bytes:
    """大端 16 位。"""
    return bytes([(value >> 8) & 0xFF, value & 0xFF])


def _be32(value: int) -> bytes:
    """大端 32 位。"""
    return bytes(
        [
            (value >> 24) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]
    )


def pack_cmd(cmd: int, data: bytes) -> str:
    """XD(cmd, data)：base64(大端 cmd 两字节 ++ data)。"""
    return base64.b64encode(_be16(cmd) + data).decode()


def build_wake_payload(uid: str) -> str:
    """拼唤醒门锁的指令（拍照监控）。

    **开锁前必须先把门锁叫醒**：门锁睡着时，服务端只是把开锁指令缓存起来
    （CmdCache 有效期 60 秒），设备没醒过来指令就过期了——服务端照样回
    「已接收」，但门锁那边根本没收到，表现就是「点了开锁门没反应」。

    「拍照监控」是王力 App 自己用的探活/唤醒指令：设备会真的回一包
    （应答里带账号 uid），回包到了就说明设备已经在线，开锁指令随后就能送到。
    副作用是门锁会拍一张照，事件流里会多一条 ACTIVE_MONITOR。
    """
    uid_bytes = uid.encode()
    size = len(uid_bytes)
    return pack_cmd(CMD_SELFVIEW, bytes([size + 2, 1, size]) + uid_bytes)


def build_unlock_payload(uid: str, pk: str = "", seconds: int = UNLOCK_TTL_SECONDS) -> str:
    """拼远程开锁指令。

    ``uid`` 是账号 uid（王力 App 用的就是 ``login.profile.uid``），
    ``pk`` 是门锁的协议号，``seconds`` 是指令有效期。
    """
    if not pk.startswith("1002"):
        # 老协议：门密码开锁，标志位 1 = 开锁
        return pack_cmd(CMD_DOORPW, bytes([1]))

    uid_bytes = uid.encode()
    size = len(uid_bytes)
    # RMUNLK 载荷：[长度+2, 标志位, uid 长度, uid...]
    inner = bytes([size + 2, 1, size]) + uid_bytes
    body = (
        _be16(size + 11)  # 后续长度
        + _be32(seconds)  # 指令有效期（秒）
        + _be16(size + 5)  # 命令块长度
        + _be16(CMD_RMUNLK)
        + inner
    )
    return pack_cmd(CMD_CMDCACHE, body)
