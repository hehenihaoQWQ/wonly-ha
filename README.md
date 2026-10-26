# 王力智能门锁（Home Assistant 集成）

把王力（KiwiOT 白标，`go.kiwik.cn`）智能门锁接入 Home Assistant：
用王力 App 的账号登录后，拿到 token 与门锁数据，暴露成标准的 `lock` / `sensor` / `event` 实体，
可以直接用来做回家 / 离家自动化。

## 功能

- **登录换 token**：用王力 App 的手机号 + 密码登录，token 自动续期
- **实时状态**：WebSocket 长连接（`wss://wsapi.kiwiot.com`），开锁 / 上锁事件秒级推送，断线自动重连
- **远程开锁**：`lock.unlock` 走王力自己的 secureToken 鉴权，和 App 一样（需先配置「开锁密码」）
  - 开锁前会自动先唤醒门锁（见下面的「开锁前必须唤醒门锁」）
- **事件实体**：门锁事件直接进 HA 事件总线，自动化用 `event_type` 触发
- **开锁方式 / 开锁用户**：指纹、密码、人脸、门卡…以及是谁开的

## 安装

### 1. 添加自定义仓库

HACS → 左侧菜单「自定义仓库」→ 添加：

- 仓库地址：`https://github.com/hehenihaoQWQ/wonly-ha`
- 分类：`集成`

### 2. 安装

HACS → 集成 → 搜索「王力智能门锁」→ 下载 → 重启 Home Assistant。

### 3. 添加账号

设置 → 设备与服务 → 「添加集成」→ 搜索「王力智能门锁」→ 填王力 App 的账号密码（国内手机号，例如 `+8613930810820`）。

### 4. 填「开锁密码」（远程开锁要用）

远程开锁时王力服务端要单独校验一次凭证，校验的是你账号的**开锁密码（安全密码，最多 6 位）**，
不是登录密码。所以要额外填一次：

- 加集成时可以直接填在「开锁密码」这一栏；
- 已经加过的，在「设备与服务 → 王力智能门锁 → ⚙️ 配置」里重新配置补填，不用删掉重加。

> 开锁密码在哪：手机王力 App → 我的 → 账号安全 / 安全设置 → 开锁密码。
> 如果当初没设过，在 App 里设一个（≤6 位）再回来填。

## 实体

每个门锁会生成下面这些实体（设备名取分组名，门锁本身没有名字时）：

| 实体 | 平台 | 说明 |
| --- | --- | --- |
| `lock.<设备名>_门锁` | lock | 标准门锁实体，支持远程开锁 |
| `sensor.<设备名>_门锁状态` | sensor | 已上锁 / 已开锁 |
| `sensor.<设备名>_最近事件时间` | sensor | 最近一次事件的时间戳 |
| `event.<设备名>_门锁事件` | event | 门锁事件，驱动自动化 |

`门锁状态` 传感器的属性：

| 属性 | 含义 |
| --- | --- |
| 设备ID | 门锁 did |
| 事件 | 最近一次开关锁事件名 |
| 事件类型 | INFO / CRITICAL |
| 开锁方式 | 指纹 / 密码 / 人脸 / 门卡 / 手机 / 钥匙 … |
| 开锁用户 | 门锁用户别名（没设别名时是「指纹 3」这种） |
| 事件时间 | 服务端时间（UTC） |
| 图片地址 | 抓拍图片链接（部分事件带） |

## 事件类型

`event.<设备名>_门锁事件` 的 `event_type` 用协议原始名：

| event_type | 含义 |
| --- | --- |
| `UNLOCKED` | 已开锁 |
| `LOCKED` | 已上锁 |
| `LOCK_INDOOR_BUTTON_UNLOCK` | 室内按钮开锁 |
| `LOCK_INDOOR_LEVER_UNLOCK` | 室内把手开锁 |
| `EMERGENCY_UNLOCK` | 紧急开锁 |
| `DOOR_LOCK_UNLOCKED_KNOB` | 旋钮开锁 |
| `ACTIVE_MONITOR` | 拍照监控 |
| `REMOTE_UNLOCK` | 远程开锁 |

属性里另有中文的「事件」字段。

## 自动化示例

### 回家：门开 1 分钟后开灯

```yaml
triggers:
  - trigger: event
    event_type: UNLOCKED
    event_data:
      deviceID: 3E8F5DDCB440
conditions: []
actions:
  - action: light.turn_on
    target:
      entity_id: light.客厅灯组
    data:
      transition: 2
mode: single
```

### 离家：门锁上锁后关灯

```yaml
triggers:
  - trigger: state
    entity_id: lock.我的家_门锁
    to: locked
conditions: []
actions:
  - action: light.turn_off
    target:
      entity_id: light.客厅灯组
mode: single
```

### 通知：有人开门就发消息

```yaml
triggers:
  - trigger: event
    event_type: UNLOCKED
conditions: []
actions:
  - action: notify.send_message
    data:
      message: "门开了，开锁方式：{{ trigger.event.data['开锁方式'] }}"
mode: single
```

## 已知限制

- **不支持远程上锁**。这一系列门锁的 `lock.lock` 会在实体上直接报「该门锁不支持远程上锁，请在门内侧上锁」。
- **远程开锁必须填「开锁密码」**。这是王力服务端的要求：远程开锁要用账号的「开锁密码」（安全密码，≤6 位）
  单独换一次凭证，只填登录密码时服务端会回「已接收」但门锁不动作。
  在「设备与服务 → 王力智能门锁 → 配置」里补填即可（已实测可远程开锁）。
- **没有单独的「打开」动作**。`lock.open` 会报「该门锁没有单独的「打开」动作，请用「开锁」」。
  注意 `LockEntityFeature.OPEN` 指的是死锁那种单独的「打开」，**不是**「支持开锁」；
  声明了它 HA 会多渲染一个「打开」按钮，点了必然报错。开锁不需要任何 feature 标志。
- 门锁的实时状态靠事件流推断：服务端只给事件列表，没有单独的「当前是否上锁」接口。设备离线时状态会保持上一次的值。
- 王力服务端有接口限流，登录 / 拉取过于频繁会返回 429。集成内部已经做了 5 分钟轮询 + 复用 token。
- 密码会保存在 Home Assistant 的配置项存储里（`.storage/core.config_entries`），和社区版 `kiwiot_ws` 的做法一致。

## 实现说明

王力 H5 是 KiwiOT（优智云家）的白标，后端与 `h5.kiwik.cn` 一致，只有前端、realm 和 clientId 不同。

- 登录：`POST /restapi/auth/tokens`，body `{auth_type:"password", identifier, credential}`，header `X-Kiwik-Client-Id`，返回 `access_token`（有效期 24 小时）
  - 注意：`POST /restapi/session/token` 只返回 `session_token`（JWT），不能当 access_token 用
- 业务接口带 `?access_token=`：`/restapi/user`、`/restapi/groups`、`/restapi/groups/{gid}/devices`、`/api/devices/{did}/events`、`/api/locks/{did}/users`
- 远程开锁：先 `POST /restapi/users/{uid}/mfa/tokens` 换 secureToken，再通过 WebSocket 下发 `Iot.Device/Ctrl`
  - **`auth_type` 决定门锁认不认这个令牌**，这是远程开锁能不能真正开动门的关键：
    - `secure_password` + 账号的「开锁密码」（≤6 位）→ 门锁会执行
    - `password` + 登录密码 → 服务端会回「已接收」，但门锁那边不认，锁不会动
  - 王力 App 的逻辑：账号只要设过开锁密码，远程开锁默认就走 `secure_password`
  - WebSocket 帧：`{"header":{"namespace":"Iot.Device","name":"Ctrl","messageId":uuid,"payloadVersion":1,"secureToken":jwt},"payload":{"did":...,"verify":true,"channel":0,"data":...}}`
- 指令打包（与王力 App 一致）：`XD(cmd, data) = base64(大端 cmd 两字节 ++ data)`
  - **字节序是大端**：App 用 `DataView.setInt16(0, cmd)` 且没传 `littleEndian`，DataView 默认大端；
    它自己的解析函数 `ET()` 也按大端读。按小端理解的话，服务端会 ACK 但门锁不动作。
- 远程开锁的指令内容按门锁的 `pk`（12 位协议号）分两种：
  - `pk` 以 `1002` 开头：`CMDCACHE(5638)` 套一层 `RMUNLK(5132)`，指令里必须带账号 uid
    ```
    [BE16 后续长度][BE32 有效期秒=60][BE16 命令块长][BE16 RMUNLK][len+2,标志位1,uid长度,uid...]
    ```
  - 其它 pk：直接 `DOORPW(2063) + [1]`
- 事件：WebSocket `Iot.Device/EventNotify`，心跳 `Iot.Application/Ping`

### 开锁前必须唤醒门锁

门锁是电池供电的，会睡着。**睡着的时候开锁指令送不到设备**：
服务端只是把指令缓存起来（CmdCache 有效期 60 秒），设备没醒过来指令就过期了，
但服务端照样回一个「已接收」——于是 HA 显示开锁成功，门却纹丝不动。

所以每次远程开锁前，集成会先发一条「拍照监控」（`SELFVIEW`，指令码 5134）把门锁叫醒，
等它回包（应答里带账号 uid，说明设备真的在线）再下发开锁指令。

- 「拍照监控」是王力 App 自己用的探活/唤醒指令，设备会真的回一包
- 副作用：门锁会拍一张照，事件流里多一条 `ACTIVE_MONITOR`，`门锁状态` 传感器的「图片地址」也会更新
- 王力 App 里的「唤醒门锁」按钮用的是另一条指令（`WAKETM` 4362），实测服务端受理但设备不醒，没用

### 必须自带 User-Agent

王力网关会按 `User-Agent` 拦请求：带 `Home Assistant/...` 的请求在 `/api/locks/{did}/users`
上直接返回 `403 {"message":"Forbidden"}`（同样的 URL 换个 UA 就是 200）。
所以所有请求都显式带上 `User-Agent: KiwiOT-Wonly`，别改回 HA 默认 UA。

另外：只有 `/restapi/auth/tokens` 返回的 `access_token` 能过业务接口，
`/restapi/session/token` 的 `session_token` 会报 `401 The access token is missing`。

## 许可证

MIT
