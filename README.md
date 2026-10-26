# 王力智能门锁（Home Assistant 集成）

把王力（KiwiOT 白标，`go.kiwik.cn`）智能门锁接入 Home Assistant：
用王力 App 的账号登录后，拿到 token 与门锁数据，暴露成标准的 `lock` / `sensor` / `event` 实体，
可以直接用来做回家 / 离家自动化。

## 功能

- **登录换 token**：用王力 App 的手机号 + 密码登录，token 自动续期
- **实时状态**：WebSocket 长连接（`wss://wsapi.kiwiot.com`），开锁 / 上锁事件秒级推送，断线自动重连
- **远程开锁**：一个「开门」按钮，按一下走王力自己的 secureToken 鉴权，和 App 一样（需先配置「开锁密码」）
  - 开锁前会自动先唤醒门锁（见下面的「开锁前必须唤醒门锁」）
- **事件实体**：门锁事件进 HA 事件总线，也进 `event.<设备名>_门锁事件` 实体，两种方式都能写自动化
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
| `button.<设备名>_开门` | button | 开门按钮，按一下远程开锁 |
| `sensor.<设备名>_门锁状态` | sensor | 已上锁 / 已开锁 |
| `sensor.<设备名>_最近事件时间` | sensor | 最近一次事件的时间戳 |
| `event.<设备名>_门锁事件` | event | 门锁事件，驱动自动化 |

> 这一系列门锁**没有远程上锁**，服务端也不提供「当前是否上锁」的接口（状态只能从事件流推断），
> 所以没有 `lock` 实体——前端会把 `lock` 渲染成一个可开可关的开关，容易让人误以为还能远程上锁。
> 开门用 `button`，当前状态看「门锁状态」传感器。

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

> 「开锁方式」在**实时推送**和**事件列表**里是两种编码（数字 / 字符串），集成已经统一成同一套中文，
> 所以同一个远程开锁不会一会儿显示「远程」一会儿显示「手机」。

## 自动化示例

门锁事件的属性里，「开锁方式」是中文：`指纹` / `密码` / `人脸` / `门卡` / `钥匙` / `旋钮` / `室内按钮` / `室内把手` / `远程`。
**「远程」= 远程开锁（HA 按钮或王力 App）**，其余都是人在门那边用指纹、密码这些开的门。

> **HA 2026.10 起**：事件实体不再自动往事件总线发事件，要用新的 `event.received` 触发器
> （写自动化时实体选 `target:`，不是顶层 `entity_id:`）。
> 本集成另外自己往事件总线补发了一发，所以老的 `trigger: event` 写法也照样能用。

### 回家：晚上九点后从外面开门（非远程）开灯

```yaml
triggers:
  - trigger: event.received
    target:
      entity_id: event.wo_de_jia_men_suo_shi_jian
    options:
      event_type:
        - UNLOCKED
conditions:
  - condition: time
    after: "21:00:00"
  - condition: template
    value_template: "{{ trigger.to_state.attributes.get('开锁方式') != '远程' }}"
actions:
  # 1) 先给墙上开关上电。灯是接在智能开关继电器上的，继电器不通电时，
  #    HA 里灯照样显示 on，但物理上是不亮的 —— 不先上电，后面点灯白点。
  #    客厅三开 左键 = 客厅边吊洗墙灯组，客厅三开 中键 = 斗胆灯，玄关单开 = 玄关灯组
  - action: switch.turn_on
    target:
      entity_id:
        - switch.090615_cn_2158030396_akps3_on_p_2_1
        - switch.090615_cn_2158030396_akps3_on_p_3_1
        - switch.090615_cn_2204851766_akps1_on_p_2_1
  # 2) 等灯重新上电上线（实测 3~18 秒）
  - delay: "00:00:20"
  # 3) 玄关灯组 + 客厅边吊洗墙灯组 + 斗胆灯主灯：亮度 70%、3500K
  - action: light.turn_on
    target:
      entity_id:
        - light.mijia_cn_group_2109228834099716098_group3_s_2_light
        - light.mijia_cn_group_2108940368929230849_group3_s_2_light
        - light.lemesh_cn_1185193881_wyrb02_s_2_light
    data:
      brightness_pct: 70
      color_temp_kelvin: 3500
  # 4) 斗胆灯氛围灯：亮度 70%，不设色温（它只支持亮度）
  - action: light.turn_on
    target:
      entity_id: light.lemesh_cn_1185193881_wyrb02_s_7_ambient_light
    data:
      brightness_pct: 70
mode: single
```

> 「开锁方式」为「远程」时说明是远程开的门，条件里排除掉，就不会因为手机上远程开门而误开灯。
>
> **灯的状态别只看 HA**：`state=on` 只说明开关/灯组是开着的，亮度可能是 0，物理上照样不亮。
> 米家「灯组」更是云端虚拟设备，它报的亮度和成员灯的实际亮度经常对不上。
> 要确认灯亮了没有，看组内成员灯实体，或者直接问人。

#### 要「一上来就是我说的参数」，得先改灯的「上电默认状态」

灯的 `select.<设备>_default_power_on_state_p_2_4`（milg05）/ `_p_2_9`（lemesh wyrb02）默认是 **「上电打开」**：
上电那一刻灯按**默认色温 6500K** 亮，等自动化把 3500K 发下去才变——中间那一下"闪冷白"躲不掉。
实测断电再上电，恢复出来的是 **255/6500K**，不是你上次设的 3500K（设备并不记住上次的色温）。

改成 **「断电记忆」** 后，灯把断电前的状态和参数原样恢复：上电瞬间就是 70%/3500K，没有中间值。
（实测：11 盏射灯断电 30 秒再上电，全程每 2 秒采样，只出现过 `(on, 178, 3500)` 这一个值。）

```yaml
- action: select.select_option
  target:
    entity_id: select.090615_cn_2142748148_milg05_default_power_on_state_p_2_4
  data:
    option: 断电记忆
```

两个要注意的地方：

- **前提是每次用完这组灯都停在你要的参数上**——它记住的是"断电那一刻"的状态和参数。
  如果你白天在米家 App 里把色温改了，下次上电恢复的就是那个值。
- **墙上开关单独按不一定能点亮灯**：断电记忆 = 恢复上次状态，上次是灭的就还是灭的。
  自动化里那句 `light.turn_on` 就是兜底（灯上次是灭的时候由它点亮）。

老写法（事件总线）同样有效：

```yaml
triggers:
  - trigger: event
    event_type: UNLOCKED
    event_data:
      设备ID: 3E8F5DDCB440
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.get('开锁方式') != '远程' }}"
actions:
  - action: light.turn_on
    target:
      entity_id: light.mijia_cn_group_2108940368929230849_group3_s_2_light
mode: single
```

> 事件的 `event_data` 用的是属性名「设备ID」（中文），不是 `deviceID`。

### 离家：门锁上锁后关灯

```yaml
triggers:
  - trigger: event.received
    target:
      entity_id: event.wo_de_jia_men_suo_shi_jian
    options:
      event_type:
        - LOCKED
conditions: []
actions:
  - action: light.turn_off
    target:
      entity_id: light.mijia_cn_group_2108940368929230849_group3_s_2_light
mode: single
```

### 通知：有人开门就发消息

```yaml
triggers:
  - trigger: event.received
    target:
      entity_id: event.wo_de_jia_men_suo_shi_jian
    options:
      event_type:
        - UNLOCKED
conditions: []
actions:
  - action: notify.send_message
    data:
      message: "门开了，开锁方式：{{ trigger.to_state.attributes.get('开锁方式') }}"
mode: single
```

## 已知限制

- **不支持远程上锁**。这一系列门锁只能远程开锁，上锁得在门内侧做，所以集成只给「开门」按钮，不给 `lock` 实体。
- **远程开锁必须填「开锁密码」**。这是王力服务端的要求：远程开锁要用账号的「开锁密码」（安全密码，≤6 位）
  单独换一次凭证，只填登录密码时服务端会回「已接收」但门锁不动作。
  在「设备与服务 → 王力智能门锁 → 配置」里补填即可（已实测可远程开锁）。
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
