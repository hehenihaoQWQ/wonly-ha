"""王力门锁 WebSocket 长连接。

一条连接同时干两件事：
1. 被动接收 Iot.Device/EventNotify 事件（开锁/上锁推送）
2. 主动下发 Iot.Device/Ctrl 指令（远程开锁）并等 CtrlResponse / ErrorResponse
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

import aiohttp

from .api import WonlyApi, WonlyApiError
from .const import WS_HEARTBEAT_SECONDS

_LOGGER = logging.getLogger(__name__)

EventCallback = Callable[[str, dict[str, Any]], None]


class WonlyConnection:
    """管理一条王力门锁 WebSocket。"""

    def __init__(self, api: WonlyApi, on_event: EventCallback) -> None:
        self._api = api
        self._on_event = on_event
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._reader: asyncio.Task | None = None
        self._heartbeat: asyncio.Task | None = None
        self._closed: asyncio.Event = asyncio.Event()

    @property
    def connected(self) -> bool:
        """连接是否可用。"""
        return self._ws is not None and not self._ws.closed

    async def async_connect(self) -> None:
        """建立连接并起心跳/收消息两个协程。"""
        self._closed.clear()
        self._ws = await self._api.async_ws_connect()
        self._reader = asyncio.create_task(self._read_loop())
        self._heartbeat = asyncio.create_task(self._heartbeat_loop())
        _LOGGER.info("王力门锁 WebSocket 已连接")

    async def async_wait_closed(self) -> None:
        """等待连接断开。"""
        await self._closed.wait()

    async def async_close(self) -> None:
        """关闭连接并取消后台任务。"""
        for task in (self._reader, self._heartbeat):
            if task is not None:
                task.cancel()
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    async def async_ctrl(
        self,
        did: str,
        data: str,
        secure_token: str | None = None,
        timeout: float = 15,
    ) -> dict[str, Any]:
        """下发一条设备指令并等待应答。"""
        if not self.connected:
            raise WonlyApiError("王力门锁 WebSocket 未连接，无法下发指令")

        message_id = await self._api.async_message_id()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        try:
            await self._api.async_send_ctrl(
                self._ws, did, data, secure_token, message_id
            )
            try:
                return await asyncio.wait_for(future, timeout)
            except TimeoutError:
                raise WonlyApiError("等待王力门锁应答超时") from None
        finally:
            self._pending.pop(message_id, None)

    async def async_wake(
        self, did: str, payload: str, timeout: float = 8
    ) -> bool:
        """发一条唤醒指令，等设备回应。

        门锁睡着的时候，服务端发过去的开锁指令只是被缓存起来，设备没醒就过期了，
        服务端照样回「已接收」但门锁没反应。先用「拍照监控」把设备叫醒，
        收到它的回包才说明设备真的在线。
        """
        if not self.connected:
            return False
        try:
            response = await self.async_ctrl(did, payload, None, timeout)
        except WonlyApiError as err:
            _LOGGER.info("唤醒门锁 %s 没有回应: %s", did, err)
            return False
        header = response.get("header") or {}
        if header.get("name") == "ErrorResponse":
            _LOGGER.info("唤醒门锁 %s 被服务端拒绝: %s", did, response.get("payload"))
            return False
        return True

    # ---------- 内部 ----------
    async def _read_loop(self) -> None:
        """持续收消息，分发给事件回调或等待中的指令。"""
        ws = self._ws
        assert ws is not None
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                self._dispatch(data)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("王力门锁 WebSocket 读取异常: %s", err)
        finally:
            self._closed.set()

    def _dispatch(self, data: dict[str, Any]) -> None:
        """按消息类型分发。"""
        header = data.get("header") or {}
        name = header.get("name")
        namespace = header.get("namespace")

        if namespace == "Iot.Device" and name == "EventNotify":
            payload = data.get("payload") or {}
            did = payload.get("did")
            if did:
                _LOGGER.info("收到门锁事件 %s: %s", did, payload.get("name"))
                self._on_event(did, payload)
            return

        if name in ("CtrlResponse", "ErrorResponse"):
            message_id = header.get("messageId")
            future = self._pending.get(message_id)
            if future is None and len(self._pending) == 1:
                # 服务端个别情况下不回 messageId，只有一个待处理指令时直接归它
                future = next(iter(self._pending.values()))
            if future is not None and not future.done():
                future.set_result(data)

    async def _heartbeat_loop(self) -> None:
        """30 秒一次心跳。"""
        ws = self._ws
        assert ws is not None
        try:
            while True:
                await asyncio.sleep(WS_HEARTBEAT_SECONDS)
                await self._api.async_ping(ws)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("王力门锁 WebSocket 心跳异常: %s", err)
