"""王力智能门锁 (KiwiOT) 接口客户端。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import aiohttp

from .const import BASE_URL, DEFAULT_CLIENT_ID, WS_URL

_LOGGER = logging.getLogger(__name__)

# 王力/KiwiOT 的网关会按 User-Agent 拦截请求：
# 带 "Home Assistant/..." 的请求在 /api/locks/{did}/users 上直接返回 403 Forbidden，
# 换成别的 UA 就正常。所以这里固定一个自己的 UA。
USER_AGENT = "KiwiOT-Wonly"


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
        self._logged_conn = False

    # ---------- 内部 ----------
    def _headers(
        self,
        extra: dict[str, str] | None = None,
        *,
        auth: bool = False,
        bearer: bool = False,
    ) -> dict[str, str]:
        """请求头。

        业务查询只把 access_token 放在 URL 上（和王力 App、社区版 kiwiot_ws 一致）；
        只有登录 / 换开锁凭证这类需要 client id 的请求才加额外的头。
        """
        headers: dict[str, str] = {"User-Agent": USER_AGENT}
        if auth:
            headers["X-Kiwik-Client-Id"] = self._client_id
        if bearer and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if extra:
            headers.update(extra)
        return headers

    def _redacted_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """请求头（token 打码），排查问题时用。"""
        result = dict(headers or {})
        if "Authorization" in result:
            result["Authorization"] = "Bearer ***"
        return result

    @staticmethod
    def _peer(resp: aiohttp.ClientResponse) -> str:
        """取对端 / 本地地址 / TLS 信息，出问题时定位用。"""
        connection = resp.connection
        transport = connection.transport if connection else None
        if transport is None:
            return "连接信息不可用"
        peer = transport.get_extra_info("peername") or ()
        sock = transport.get_extra_info("sockname") or ()
        fmt = lambda a: f"{a[0]}:{a[1]}" if len(a) >= 2 else str(a)  # noqa: E731
        ssl_obj = transport.get_extra_info("ssl_object")
        tls = ""
        if ssl_obj is not None:
            cipher = ssl_obj.cipher()
            tls = f"{ssl_obj.version()}/{cipher[0] if cipher else '?'}"
        return f"对端={fmt(peer)} 本地={fmt(sock)} TLS={tls or '无'}"

    async def _request(
        self,
        method: str,
        path: str,
        body: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 20,
    ) -> Any:
        url = f"{self._base_url}{path}"
        query = dict(params or {})
        if self._token:
            query.setdefault("access_token", self._token)
        request_headers = headers if headers is not None else self._headers()

        try:
            async with self._session.request(
                method,
                url,
                headers=request_headers,
                json=body,
                params=query,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                # 连接信息要在读 body 之前取，读完连接可能已经还回连接池
                peer = self._peer(resp)
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
                    _LOGGER.error(
                        "王力接口 %s %s 失败: %s %s | %s | 协议=%s | 请求头=%s | 响应头=%s | 响应体=%s",
                        method,
                        path,
                        resp.status,
                        resp.reason,
                        peer,
                        resp.version,
                        self._redacted_headers(request_headers),
                        {
                            k: v
                            for k, v in resp.headers.items()
                            if k.lower()
                            in (
                                "server",
                                "via",
                                "content-type",
                                "x-cache",
                                "x-request-id",
                                "x-served-by",
                                "retry-after",
                                "x-ratelimit-limit",
                                "x-ratelimit-remaining",
                                "alibaba-request-id",
                                "eagleeye-traceid",
                            )
                        },
                        text[:300],
                    )
                    raise WonlyApiError(f"{method} {path} -> {resp.status}: {message}")
                if not self._logged_conn:
                    self._logged_conn = True
                    _LOGGER.info(
                        "王力接口连接: %s | 协议=%s | 请求头=%s",
                        peer,
                        resp.version,
                        self._redacted_headers(request_headers),
                    )
                return data
        except aiohttp.ClientError as err:
            raise WonlyApiError(f"{method} {path} 网络错误: {err}") from err

    # ---------- 登录 ----------
    async def async_login(self, identifier: str, credential: str) -> str:
        """用账号密码换 access_token，成功返回 token。"""
        body = {"auth_type": "password", "identifier": identifier, "credential": credential}
        last: Exception | None = None
        # 重新登录时不要把失效的旧 token 带到 URL 上
        old_token = self._token
        self._token = None
        try:
            for path in ("/restapi/auth/tokens", "/restapi/session/token"):
                try:
                    data = await self._request(
                        "POST",
                        path,
                        body,
                        headers=self._headers(
                            {"Content-Type": "application/json"}, auth=True
                        ),
                    )
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
        except Exception:
            self._token = old_token
            raise
        self._token = old_token
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
            headers=self._headers(
                {"Content-Type": "application/json"}, auth=True, bearer=True
            ),
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
        data: str,
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
                "payload": {"did": did, "verify": True, "data": data},
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
