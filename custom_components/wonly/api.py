"""王力智能门锁 (KiwiOT) 接口客户端。"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import aiohttp

from .const import BASE_URL, CMD_DOORPW, DEFAULT_CLIENT_ID, WS_URL

_LOGGER = logging.getLogger(__name__)

# 远端开锁指令：门密码开锁(DOORPW=2063) + 标志位 1
# 王力 App 的打包方式是 XD(cmd, data) = base64(小端 cmd 两字节 ++ data)，
# 这里保持完全一致（标准 base64、保留补位符）。
UNLOCK_PAYLOAD = base64.b64encode(
    bytes([CMD_DOORPW & 0xFF, CMD_DOORPW >> 8, 0x01])
).decode()  # -> "DwgB"


class WonlyApiError(Exception):
    """接口调用失败。"""


class WonlyApi:
    """王力 REST + WebSocket 客户端。"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str = DEFAULT_CLIENT_ID,
        base_url: str = BASE_URL,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._uid: str | None = None
        self._expires_at: float = 0.0

    # ---------- 内部 ----------
    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Kiwik-Client-Id": self._client_id,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if extra:
            headers.update(extra)
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        body: Any = None,
        params: dict[str, Any] | None = None,
        timeout: int = 20,
    ) -> Any:
        url = f"{self._base_url}{path}"
        query = dict(params or {})
        if self._token:
            query.setdefault("access_token", self._token)

        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                json=body,
                params=query,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                text = await resp.text()
                try:
                    data = json.loads(text) if text else {}
                except ValueError:
                    data = {"raw": text}

                if resp.status >= 400:
                    message = (
                        data.get("message")
                        or data.get("error_description")
                        or data.get("message_id")
                        or text[:200]
                    )
                    raise WonlyApiError(f"{method} {path} -> {resp.status}: {message}")
                return data
        except aiohttp.ClientError as err:
            raise WonlyApiError(f"{method} {path} 网络错误: {err}") from err

    # ---------- 登录 ----------
    async def async_login(self, identifier: str, credential: str) -> str:
        """用账号密码换 access_token，成功返回 token。"""
        body = {"auth_type": "password", "identifier": identifier, "credential": credential}
        last: Exception | None = None
        for path in ("/restapi/session/token", "/restapi/auth/tokens"):
            try:
                data = await self._request("POST", path, body)
            except WonlyApiError as err:
                last = err
                continue
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            token = payload.get("access_token")
            if token:
                self._token = token
                expires_in = payload.get("expires_in") or 0
                self._expires_at = time.time() + float(expires_in) - 300
                _LOGGER.info("王力登录成功，token 有效期 %s 秒", expires_in)
                return token
            last = WonlyApiError(f"{path} 响应中没有 access_token")
        raise WonlyApiError(f"登录失败: {last}")

    async def async_ensure_token(self, identifier: str, credential: str) -> str:
        """token 过期或缺失时重新登录。"""
        if not self._token or time.time() >= self._expires_at:
            return await self.async_login(identifier, credential)
        return self._token

    # ---------- 业务接口 ----------
    async def async_get_user(self) -> dict[str, Any]:
        data = await self._request("GET", "/restapi/user")
        self._uid = data.get("uid")
        return data

    async def async_get_groups(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/restapi/groups")
        if isinstance(data, dict):
            data = data.get("data") or []
        return data or []

    async def async_get_group_devices(self, gid: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/restapi/groups/{gid}/devices")
        if isinstance(data, dict):
            data = data.get("data") or []
        return data or []

    async def async_get_device(self, did: str) -> dict[str, Any]:
        return await self._request("GET", f"/restapi/devices/{did}")

    async def async_get_events(self, did: str, per_page: int = 10) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/api/devices/{did}/events", params={"page": 1, "per_page": per_page}
        )
        if isinstance(data, dict):
            data = data.get("data") or []
        return data or []

    async def async_get_lock_users(self, did: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/api/locks/{did}/users")
        if isinstance(data, dict):
            data = data.get("data") or []
        return data or []

    async def async_create_secure_token(self, uid: str, credential: str) -> str:
        """换远程开锁用的 secureToken（用账号密码即可，无需 6 位开锁密码）。"""
        data = await self._request(
            "POST",
            f"/restapi/users/{uid}/mfa/tokens",
            body={"auth_type": "password", "credential": credential},
        )
        token = data.get("access_token")
        if not token:
            raise WonlyApiError("获取远程开锁凭证失败：响应中没有 access_token")
        return token

    # ---------- WebSocket ----------
    async def async_ws_connect(self) -> aiohttp.ClientWebSocketResponse:
        if not self._token:
            raise WonlyApiError("WebSocket 连接前需要先登录")
        return await self._session.ws_connect(
            f"{WS_URL}?access_token={self._token}",
            heartbeat=None,
            timeout=aiohttp.ClientTimeout(total=30),
        )

    async def async_send_ctrl(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        did: str,
        secure_token: str,
        message_id: str | None = None,
    ) -> str:
        """下发开锁指令，返回 messageId 便于对响应。"""
        message_id = message_id or await self.async_message_id()
        await ws.send_json(
            {
                "header": {
                    "namespace": "Iot.Device",
                    "name": "Ctrl",
                    "messageId": message_id,
                    "payloadVersion": 1,
                    "secureToken": secure_token,
                },
                "payload": {"did": did, "verify": True, "data": UNLOCK_PAYLOAD},
            }
        )
        _LOGGER.info("已下发开锁指令给 %s", did)
        return message_id

    @staticmethod
    async def async_message_id() -> str:
        """生成消息 id（UUID v4 形态）。"""
        import uuid

        return str(uuid.uuid4())

    async def async_ping(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        await ws.send_json(
            {
                "header": {
                    "namespace": "Iot.Application",
                    "name": "Ping",
                    "messageId": await self.async_message_id(),
                    "payloadVersion": 1,
                }
            }
        )
