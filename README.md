# 王力智能门锁（Home Assistant 集成）

把王力（KiwiOT 白标，`go.kiwik.cn`）智能门锁接入 Home Assistant：
用王力 App 的账号登录后，拿到 token 与门锁数据，暴露成标准的 `lock` / `sensor` / `event` 实体，
可以直接用来做回家 / 离家自动化。

## 功能

- **登录换 token**：用王力 App 的手机号 + 密码登录，token 自动续期
- **实时状态**：WebSocket 长连接（`wss://wsapi.kiwiot.com`），开锁 / 上锁事件秒级推送，断线自动重连
- **远程开锁**：`lock.unlock` 走王力自己的 secureToken 鉴权，和 App 一样
- **事件实体**：门锁事件直接进 HA 事件总线，自动化用 `event_type` 触发
- **开锁方式 / 开锁用户**：指纹、密码、人脸、门卡…以及是谁开的

## 安装

### 1. 添加自定义仓库

HACS → 左侧菜单「自定义仓库」→ 添加：

- 仓库地址：`https://github.com/XG520/wonly-ha`
- 分类：`集成`

### 2. 安装

HACS → 集成 → 搜索「王力智能门锁」→ 下载 → 重启 Home Assistant。

### 3. 添加账号

设置 → 设备与服务 → 「添加集成」→ 搜索「王力智能门锁」→ 填王力 App 的账号密码（国内手机号，例如 `+8613930810820`）。

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
- 门锁的实时状态靠事件流推断：服务端只给事件列表，没有单独的「当前是否上锁」接口。设备离线时状态会保持上一次的值。
- 王力服务端有接口限流，登录 / 拉取过于频繁会返回 429。集成内部已经做了 5 分钟轮询 + 复用 token。
- 密码会保存在 Home Assistant 的配置项存储里（`.storage/core.config_entries`），和社区版 `kiwiot_ws` 的做法一致。

## 实现说明

王力 H5 是 KiwiOT（优智云家）的白标，后端与 `h5.kiwik.cn` 一致，只有前端、realm 和 clientId 不同。

- 登录：`POST /restapi/session/token`，body `{auth_type:"password", identifier, credential}`，header `X-Kiwik-Client-Id`
- 业务接口带 `?access_token=`：`/restapi/user`、`/restapi/groups`、`/restapi/groups/{gid}/devices`、`/api/devices/{did}/events`、`/api/locks/{did}/users`
- 远程开锁：先 `POST /restapi/users/{uid}/mfa/tokens`（`auth_type:"password"`）换 secureToken，再通过 WebSocket 下发 `Iot.Device/Ctrl`
- 指令打包（与王力 App 一致）：`base64(小端 cmd 两字节 ++ data)`，开锁是 `DOORPW(2063) + [1]`
- 事件：WebSocket `Iot.Device/EventNotify`，心跳 `Iot.Application/Ping`

## 许可证

MIT
