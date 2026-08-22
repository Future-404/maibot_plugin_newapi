# NewAPI Suite Plugin for MaiBot

> 打通 MaiBot 与 NewAPI 的管理插件，提供 **网站账号绑定、余额查询、每日签到、娱乐打劫** 以及 **管理员查询 / 解绑 / 调额** 功能。
> 插件版本：`2.6.0` ｜ 插件 ID：`future-404.maibot-plugin-newapi`

---

## 目录

1. [整体项目介绍](#1-整体项目介绍)
2. [功能一览](#2-功能一览)
3. [环境要求](#3-环境要求)
4. [安装方法](#4-安装方法)
5. [命令一览](#5-命令一览)
6. [用户命令详解](#6-用户命令详解)
7. [管理员命令详解](#7-管理员命令详解)
8. [WebUI 配置详解](#8-webui-配置详解)
9. [权限模型](#9-权限模型)
10. [数据库与数据存储](#10-数据库与数据存储)
11. [文件结构说明](#11-文件结构说明)
12. [额度换算与 NewAPI 接口说明](#12-额度换算与-newapi-接口说明)
13. [开发与验证](#13-开发与验证)
14. [常见问题与注意事项](#14-常见问题与注意事项)
15. [开源协议](#15-开源协议)

---

## 1. 整体项目介绍

`maibot_plugin_newapi` 是运行在 **MaiBot（>= 1.1.3）** 上的管理插件，使用 MaiBot 新版 Host / Runner 插件架构和 `maibot-plugin-sdk`。

插件解决的核心问题：**让聊天平台的用户（Discord / QQ / 其他）与 NewAPI 网站用户一一对应**，并在此基础上提供一套完整的额度（Quota）运营能力：

- 用户把聊天账号与自己的 NewAPI 网站用户 ID **绑定**，绑定后自动把该网站用户加入配置的会员分组。
- 用户可以随时 `/查询余额` 查看自己网站账号的真实额度。
- 用户每天可以 `/签到`，插件通过 NewAPI 管理员调额接口把奖励额度**直接写入绑定网站用户**（不需要生成兑换码、不需要用户手动兑换）。
- 用户之间可以 `/打劫`，是一个带概率、冷却、通缉、双倍的娱乐性额度转移玩法，所有规则均可由管理员在网页后台配置。
- 管理员可以通过 `/查询`、`/解绑`、`/调整余额` 管理任意绑定关系与额度。

所有额度变动都使用 **NewAPI 管理员原子调额接口 `POST /api/user/manage`**（`action: add_quota`，配合 `mode: add` / `mode: subtract`），额度直接落在目标网站用户账户上，不会创建兑换码，也不会以管理员身份冒用用户身份兑换。

---

## 2. 功能一览

| 功能 | 说明 |
|---|---|
| **账号绑定** | 平台用户 ↔ NewAPI 网站用户 ID 一一对应；绑定后自动同步网站用户组 |
| **邮箱验证绑定** | 两步绑定：`/绑定` 发送邮件验证码，`/绑定验证` 确认后完成绑定，防止误绑他人网站账号 |
| **余额查询** | 用户实时查询绑定网站账号的显示额度 |
| **每日签到** | 每天一次，奖励额度直接入账；支持随机额度、双倍概率、首签礼包 |
| **娱乐打劫** | 用户互劫余额；支持成功概率、双倍概率、失败赔付、成功冷却、失败通缉，全部参数可配置 |
| **回复自动 @ 用户名** | 所有命令回复都会在文本前自动 @ 触发命令的用户名（Discord @提及，方便定向回复） |
| **管理员查询** | 按网站 ID / 用户 ID / @用户名 查询绑定详情 |
| **管理员解绑** | 解除绑定并自动把网站用户恢复到解绑分组 |
| **管理员调额** | 给指定绑定账号增加正数额度 |
| **WebUI 全量配置** | 所有规则、概率、时间、话术均可在 MaiBot 网页后台配置 |
| **防刷与一致性** | SQLite WAL、签到/打劫原子占位、网站 ID 唯一约束、跨账户失败补偿 |
| **话术模板** | 签到成功、打劫成功/失败/冷却/通缉等文案均支持模板变量自定义 |

---

## 3. 环境要求

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| **MaiBot** | `>= 1.1.3` | 新版 Host/Runner 插件架构 |
| **maibot-plugin-sdk** | `>= 2.0.0`（建议随宿主版本，如 `>= 2.7.1`） | 插件运行依赖 |
| **NewAPI** | 最新版 | 需要管理员 PAT，且对新 API 用户具备管理权限 |
| **Python** | 3.10+ | 运行 `httpx`、`pydantic` 等依赖 |

> MaiBot 会通过 `_manifest.json` 自动为插件安装 `httpx` 依赖，无需手动安装到宿主机。

---

## 4. 安装方法

### 4.1 放入插件目录

把整个项目目录（即本仓库）复制到 MaiBot 的 `plugins` 文件夹下，例如：

```text
MaiBot/
└── plugins/
    └── maibot_plugin_newapi/   ← 本插件
        ├── _manifest.json
        ├── plugin.py
        ├── newapi_utils.py
        └── ...
```

### 4.2 启动并自动加载

启动 MaiBot，插件会被自动发现并加载。插件日志使用 `newapi_suite` 名称，可在 MaiBot 日志中搜索确认加载状态：

```text
[NewAPI Plugin] NewAPI 核心引擎初始化成功。
```

### 4.3 配置 API 连接

至少需要配置两项才能正常使用：

- **NewAPI 基础 URL**
- **具备管理员权限的 API 访问令牌（PAT）**

配置方式有两种（WebUI 优先）：

1. **MaiBot 网页后台** → 插件配置页（推荐，见 [第 8 节](#8-webui-配置详解)）。
2. **运行时配置文件**：在插件目录放置 `config.toml`（`[api]` 段）或 `.env` 文件。

   `config.toml` 示例：

   ```toml
   [api]
   api_base_url = "http://172.17.0.1:3000"
   api_access_token = "sk-xxxxxxx"
   ```

   `.env` 示例：

   ```env
   API_BASE_URL=http://172.17.0.1:3000
   API_ACCESS_TOKEN=sk-xxxxxxx
   ```

> ⚠️ `config.toml`、`.env`、`*.db` 已在 `.gitignore` 中排除，不会被提交。请勿把令牌写进源码。

---

## 5. 命令一览

| 命令 | 权限 | 作用 |
|---|---|---|
| `/查询余额` | 普通用户 | 查看自己绑定网站的当前额度 |
| `/绑定 <网站ID>` | 普通用户 | 两步绑定第一步：向该网站用户邮箱发送验证码 |
| `/绑定验证 <验证码>` | 普通用户 | 两步绑定第二步：输入邮箱收到的 6 位验证码完成绑定 |
| `/签到` | 普通用户 | 领取每日签到奖励额度 |
| `/打劫 @用户名` 或 `/打劫 <用户ID>` | 普通用户 | 对目标用户发起一次打劫 |
| `/查询 [@用户名 / 用户ID / 网站ID]` | 管理员 | 查询指定用户的绑定详情 |
| `/解绑 [@用户名 / 用户ID / 网站ID]` | 管理员 | 解除绑定并恢复网站用户分组 |
| `/调整余额 [@用户名 / 用户ID / 网站ID] [正数]` | 管理员 | 给指定绑定账号增加额度 |

---

## 6. 用户命令详解

### 6.1 `/查询余额`

**作用**：查看当前发送者的绑定网站账号的显示额度。

**调用方式**：

```text
/查询余额
```

**权限**：普通用户（受频道白/黑名单与私聊开关约束）。

**执行逻辑**：
1. 提取发送者聊天账号 ID。
2. 查本地绑定记录，确认已绑定。
3. 调用 NewAPI `GET /api/user/{网站ID}` 读取原始额度。
4. 按 `binding.quota_display_ratio` 换算为显示额度并回复。

**成功回复示例**：

```text
查询成功！
网站ID: 2001
当前剩余额度: 3.00
```

**常见失败**：
- 未绑定 → `您尚未绑定网站ID，无法进行此操作。`
- 无法读取网站信息 → `查询失败，无法从网站获取余额信息。`

---

### 6.2 `/绑定 <网站ID>`

**作用**：两步绑定的**第一步**。校验绑定资格后，向该网站用户资料中登记的邮箱发送 6 位数字验证码，作为账户归属的初步验证。

**调用方式**：

```text
/绑定 2001
```

**参数说明**：

| 参数 | 必填 | 说明 |
|---|---|---|
| `网站ID` | 是 | NewAPI 网站用户的数字 ID |

**权限**：普通用户。

**执行逻辑**（依次校验，任一失败即停止）：
1. 当前账号未绑定（已绑定则拒绝）。
2. 网站 ID 在 NewAPI 中存在（`GET /api/user/{id}`）。
3. 该网站 ID 未被其他用户绑定（本地唯一性检查 + 数据库唯一约束双保险）。
4. 读取该网站用户资料中的 `email` 字段；未配置邮箱则提示联系管理员。
5. 生成 6 位数字验证码，写入本地 `newapi_binding_verifications` 待验证记录（同一用户再次申请会覆盖旧记录）。
6. 通过 SMTP（465 + `SMTP_SSL`，后台线程执行）发送验证码邮件；发送失败则回滚待验证记录并提示。
7. 回复用户查看邮箱，并用 `/绑定验证 <验证码>` 完成绑定。

> 若 `email.enabled = false`（SMTP 未配置的存量部署），本命令回退为**旧版一次性绑定**：跳过验证码，直接完成绑定（改分组 + 写本地记录），不发邮件。

**成功回复示例**：

```text
验证码已发送，请查看邮箱（注意垃圾邮件箱），用 /绑定验证 <验证码> 完成绑定。验证码 300 秒内有效。
```

**常见失败**：
- 已绑定 → `您已经绑定了网站ID: xxx，无需重复绑定。`
- 网站用户不存在 → `找不到网站ID为 xxx 的用户，请检查ID是否正确。`
- 已被他人绑定 → `网站ID xxx 已被其他用户绑定。`
- 网站用户未配置邮箱 → `该网站用户未配置邮箱，无法验证身份，请联系管理员。`
- 验证码发送失败 → 提示检查 SMTP 配置（见 [第 14 节](#14-常见问题与注意事项)）。

> ⚠️ **安全说明**：`/绑定` 是自助操作。验证码绑定只证明"能收到该网站用户邮箱的邮件"，仍建议仅在可信频道启用插件，或通过 `permission.mode` / 白名单 / 私聊开关限制可用范围。

---

### 6.3 `/绑定验证 <验证码>`

**作用**：两步绑定的**第二步**。校验 `/绑定` 发送到邮箱的 6 位验证码，通过后完成绑定并把网站用户加入 `binding.binding_group` 分组。

**调用方式**：

```text
/绑定验证 123456
```

**参数说明**：

| 参数 | 必填 | 说明 |
|---|---|---|
| `验证码` | 是 | 邮箱收到的 6 位数字验证码 |

**权限**：普通用户。

**执行逻辑**：
1. 按发送者 ID 查找本地待验证记录（`newapi_binding_verifications`）。
2. 依次校验：存在记录 → 未过期（`email.code_ttl_seconds`）→ 验证码匹配。
3. 校验通过后执行与旧版一致的绑定仪式：获取网站资料 → 改 `group` 为 `binding.binding_group` → `PUT /api/user/` → 写入本地绑定记录（保存 `qq_username`）。
4. 绑定成功后清理该待验证记录；若绑定仪式失败（如远端分组更新失败）**不消耗验证码**，同码可在有效期内重试。

**失败提示**：
- 未发起申请 → `请先使用 /绑定 <网站ID> 发起绑定申请。`
- 验证码错误 → `验证码错误，请检查后重试。`
- 验证码过期 → `验证码已过期，请重新使用 /绑定 <网站ID> 获取新验证码。`
- 错误次数过多 → `验证码错误次数过多，已失效，请重新使用 /绑定 <网站ID> 获取新验证码。`（连续 5 次错误验证码即失效，防止暴力枚举；过期记录也会被清除，均需重新 `/绑定`）

---

### 6.4 `/签到`

**作用**：每天领取一次签到奖励，奖励额度直接写入绑定网站账号。

**调用方式**：

```text
/签到
```

**权限**：普通用户。

**执行逻辑**：
1. 检查 `check_in.enabled`（关闭则提示）。
2. 确认已绑定。
3. 按 `check_in.timezone_offset_hours` 计算"今天"的边界，使用 SQLite 原子占位防止同一天重复领取（并发也只会成功一次）。
4. 计算奖励：
   - 基础额度在 `check_in.min_display_quota` ~ `check_in.max_display_quota` 之间随机。
   - 按 `check_in.double_chance` 概率翻倍。
   - 若为首次签到且开启首签礼包，追加 `check_in.first_check_in_bonus_display_quota`。
5. 调用 NewAPI `POST /api/user/manage`（`mode: add`）把原始额度写入绑定网站用户。
6. 读取最新余额用于回复；若入账成功但读取余额失败，返回"已到账但余额未知"。

**成功回复示例**：

```text
签到成功！
您获得了 5.23 额度！
当前剩余总额度为 12.34。
```

**失败回滚**：若 NewAPI 入账失败，插件会**仅释放本次签到占位**，用户稍后可重试；不会把并发成功签到记录误删。

**话术模板**：见 [8.5 每日签到规则与模版](#85-每日签到规则与模版)。

---

### 6.5 `/打劫 @用户名` / `/打劫 <用户ID>`

**作用**：对目标用户发起一次打劫，涉及成功/失败/双倍/冷却/通缉，全部规则可在 WebUI 配置。

**调用方式**：

```text
/打劫 @目标用户名       # Discord/QQ 直接 @用户名
/打劫 <目标用户ID>       # 纯数字用户 ID
```

**权限**：普通用户。

**目标解析顺序**（`_resolve_target()`）：
1. 优先解析消息中的 @提及（Discord `<@ID>`、CQ `[CQ:at,qq=ID]`、消息段的 at/mention、顶层 `mentions` 数组）。
2. 其次解析纯数字用户 ID。
3. 最后把 `@用户名` 去掉 `@` 前缀，按绑定时记录的 `qq_username` 反查绑定记录得到用户 ID。

Discord 显示名可以包含空格，`/打劫 @Discord Display Name`、管理员 `/查询`、`/解绑` 和 `/调整余额 @Discord Display Name 10` 均可使用。单条命令只接受一个用户目标；包含多个不同用户提及的消息会被拒绝，避免误操作第一个被提及者。

> ⚠️ 使用 `@用户名` 打劫时，**目标必须先完成 `/绑定`**，并且绑定时插件已记录其用户名；否则无法通过用户名找到对方。

**基础校验**（任一失败即停止）：
- 打劫功能已启用（`robbery.enabled`）。
- 不能打劫自己。
- 打劫者和目标都已完成绑定。
- 额度展示比例配置有效。

**执行逻辑**：

1. **状态抢占**：使用 SQLite `BEGIN IMMEDIATE` 原子检查并记录打劫者状态，防止并发打劫绕过冷却/通缉。
2. **冷却 / 通缉检查**：
   - 若打劫者在通缉期（`wanted_until` 未到）→ 拒绝并提示剩余秒数。
   - 若打劫者处于成功冷却期（`cooldown_until` 未到）→ 拒绝并提示剩余秒数。
3. **读取双方余额**。
4. **判定结果**（`random.random() < success_chance`）：
   - **成功**：
     - 基础转移额度在 `robbery.min_display_quota` ~ `robbery.max_display_quota` 之间随机（兼容旧字段 `base_display_quota`）。
     - 按 `robbery.double_chance` 概率翻倍，翻倍后**仍不超过目标当前余额**。
     - 从目标账户 `subtract` 扣款 → 给打劫者 `add` 加款。
     - 成功后设置成功冷却 `cooldown_seconds`。
   - **失败**：
     - 从打劫者当前余额按 `failure_penalty_ratio` 计算赔付额度，受 `failure_penalty_max_display_quota` 上限约束。
     - 从打劫者 `subtract` 扣款 → 给目标 `add` 加款。
     - 失败后设置通缉 `wanted_seconds`（通缉期间不能再打劫）。
5. **一致性保障**：
   - 跨账户转账为两个独立远端请求。第二步失败时，插件会**尝试反向补偿**第一步。
   - 若第二步"网络结果未知"（如超时），插件**不会盲目补偿**，避免远端其实已入账导致的重复增发，而是返回不确定状态。
   - 若补偿也失败，记录严重日志并返回"回滚失败，请联系管理员"。

**成功回复示例**：

```text
打劫得手！
获得 6.50 额度！
当前总额度为 20.00。
```

**双倍回复示例**：

```text
打劫双倍得手！
获得 13.00 额度！
当前总额度为 26.50。
```

**失败回复示例**：

```text
打劫失败！您赔付给对方 2.10 额度，并被通缉 600 秒。
```

**冷却回复示例**：

```text
打劫冷却中，请 120 秒后再试。
```

**通缉回复示例**：

```text
您正在被通缉，请 300 秒后再试。
```

**话术模板**：见 [8.6 打劫规则与文案](#86-打劫规则与文案)。

---

## 7. 管理员命令详解

> 三个管理员命令都需要发送者在 `permission.admin_users`（用户名列表）中，否则回复 `权限不足。`。

### 7.1 `/查询 [@用户名 / 用户ID / 网站ID]`

**作用**：查询指定绑定记录。

**调用方式**：

```text
/查询
/查询 2001            # 按网站 ID 或用户 ID
/查询 @目标用户名       # 按 @用户名（目标需已绑定）
```

**权限**：管理员。

**执行逻辑**：把参数当作"网站 ID"或"用户 ID"查本地绑定表，命中任一即返回；`@用户名` 会先按绑定时记录的 `qq_username` 反查。

**成功回复示例**：

```text
查询成功！
网站ID: 2001
用户ID: 1001
```

**常见失败**：`未找到绑定记录。` / `格式错误。`

---

### 7.2 `/解绑 [@用户名 / 用户ID / 网站ID]`

**作用**：解除指定绑定，并把该网站用户在 NewAPI 的 `group` 恢复到 `binding.unbind_group`。

**调用方式**：

```text
/解绑
/解绑 2001
/解绑 @目标用户名
```

**权限**：管理员。

**执行逻辑**：
1. 解析目标绑定。
2. 调用 NewAPI `GET /api/user/{id}` 获取用户资料 → 修改 `group` 为 `unbind_group` → `PUT /api/user/` 更新。
3. **仅当远端分组恢复成功后才删除本地绑定记录**；远端失败时保留本地绑定并提示失败，方便重试。

**成功回复示例**：

```text
解绑成功。
```

**失败回复示例**：

```text
解绑失败，已保留绑定记录以便重试。
```

---

### 7.3 `/调整余额 [@用户名 / 用户ID / 网站ID] [正数]`

**作用**：给指定绑定网站账号增加正数显示额度。

**调用方式**：

```text
/调整余额 2001 5
/调整余额 2001 2.5
/调整余额 @目标用户名 10
```

**参数说明**：

| 参数 | 必填 | 说明 |
|---|---|---|
| `@用户名 / 用户ID / 网站ID` | 是 | 目标绑定 |
| `正数` | 是 | 增加的显示额度（换算后必须是整数原始额度） |

**权限**：管理员。

**执行逻辑**：
1. 解析目标绑定。
2. 用 `Decimal` 精确计算 `显示额度 × quota_display_ratio`，结果必须为整数原始额度（否则返回 `INVALID_AMOUNT`）。
3. 调用 NewAPI `POST /api/user/manage`（`mode: add`）入账。
4. 读取最新余额并回复。

**成功回复示例**：

```text
成功增加额度！当前余额: 8.00
```

**失败情况**：
- 仅支持正数：负数 / 零 → `调整失败：仅支持大于零的增加额度。`
- 换算后不是整数原始额度 → `调整失败：仅支持大于零的增加额度。`

> ⚠️ 当前版本只支持**增加**额度，不支持扣减。负号虽然能被命令正则解析，但业务上会被拒绝。

---

## 8. WebUI 配置详解

插件配置在 MaiBot 网页后台 → 插件管理 → NewAPI 插件套件 中，按配置段分组展示。以下按段逐一说明**每一个字段**。

### 8.1 插件基础设施（`plugin`）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `true` | 是否启用插件 |
| `config_version` | `2.5.0` | 配置规范版本。**不要删除**，MaiBot 用它校验配置文件结构 |

> ⚠️ 这个配置段是 MaiBot 配置文件解析的**必需契约**，不能删掉。缺少会导致 WebUI 报错 `插件配置文件缺少 [plugin] 配置节`。

---

### 8.2 NewAPI 连接设置（`api`）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `api_base_url` | 空 | NewAPI 站点地址，例如 `http://172.17.0.1:3000` 或你的外部域名。末尾不要带斜杠 |
| `api_access_token` | 空 | 管理员 PAT 或访问令牌。**必填**，必须属于有管理员角色的用户，且能管理被绑定的网站用户 |

> 若在 WebUI 留空，插件会回退读取插件目录下的 `config.toml` `[api]` 段或 `.env`。全部为空时插件无法连接 NewAPI，签到/打劫/调额不可用。

---

### 8.3 权限控制（`permission`）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `mode` | `all` | 运行模式：`all`（所有人可用）/ `whitelist`（仅白名单频道）/ `blacklist`（黑名单频道除外） |
| `whitelist` | `[]` | 白名单频道 ID 列表，`mode=whitelist` 时生效 |
| `blacklist` | `[]` | 黑名单频道 ID 列表，`mode=blacklist` 时生效 |
| `admin_users` | `[]` | **超级管理员用户名列表**。管理员命令（`/查询` `/解绑` `/调整余额`）和私聊管理员放行都依赖它 |

> ⚠️ `admin_users` 使用**用户名**（字符串）而不是数字 ID。因为 MaiBot 配置系统会把大整数 ID 当数值处理，导致 Discord snowflake 等 64 位 ID 精度丢失。请填入用户在平台上的用户名（如 Discord 用户名、QQ 昵称）。

---

### 8.4 账号绑定规则（`binding`）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `binding_group` | `vip` | 绑定成功后赋予网站用户的组别 |
| `unbind_group` | `default` | 解绑后恢复的组别 |
| `quota_display_ratio` | `500000.0` | 额度展示比例。NewAPI 的 `quota` 是原始整数额度，显示额度 = `quota / quota_display_ratio`；配置里所有"显示额度"在写回 API 前都会乘以该比例。**必须大于 0** |

---

### 8.5 每日签到规则与模版（`check_in`）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `true` | 是否启用签到功能 |
| `timezone_offset_hours` | `8` | 签到"当天"的时区偏移（小时）。中国用户填 `8` |
| `min_display_quota` | `0.1` | 签到最小显示额度 |
| `max_display_quota` | `10.0` | 签到最大显示额度（每次在 min~max 间随机） |
| `double_chance` | `0.1` | 签到翻倍概率（0~1） |
| `first_check_in_bonus_enabled` | `true` | 是否开启首次签到奖励 |
| `first_check_in_bonus_display_quota` | `100.0` | 首次签到额外奖励的显示额度 |
| `check_in_success_template` | `签到成功！\n您获得了 {display_added:.2f} 额度！\n当前剩余总额度为 {display_total:.2f}。` | 常规签到成功话术模板 |
| `check_in_doubled_template` | `奖励翻倍！获得了 {display_added:.2f} 额度！\n当前剩余总额度为 {display_total:.2f}。` | 翻倍签到成功话术模板 |
| `first_check_in_success_template` | `欢迎新人！您获得了 {display_added:.2f} 额度。\n当前剩余总额度为 {display_total:.2f}。` | 首次签到成功话术模板 |

**签到模板可用变量**：

| 变量 | 含义 |
|---|---|
| `{display_added:.2f}` | 本次到账的显示额度 |
| `{display_total:.2f}` | 到账后的总显示额度 |

> 模板格式错误时会自动回退到内置文案，不会影响命令回复。

---

### 8.6 打劫规则与文案（`robbery`）

#### 规则参数

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `true` | 是否启用打劫功能 |
| `success_chance` | `0.5` | 打劫成功概率（0~1） |
| `double_chance` | `0.1` | 成功后获得双倍额度的概率（0~1） |
| `base_display_quota` | `10.0` | **兼容旧配置**的固定转移额度。当 `min/max_display_quota` 生效时优先使用随机范围 |
| `min_display_quota` | `1.0` | 成功时随机转移额度的**最小值**（显示额度） |
| `max_display_quota` | `10.0` | 成功时随机转移额度的**最大值**（显示额度） |
| `cooldown_seconds` | `300` | 成功后的冷却秒数（`0` = 不冷却） |
| `failure_penalty_ratio` | `0.1` | 失败时按打劫者当前余额赔付给目标的比例（0~1） |
| `failure_penalty_max_display_quota` | `10.0` | 失败赔付的显示额度上限（`0` = 不设上限） |
| `wanted_seconds` | `600` | 失败后的通缉秒数，通缉期间不能再打劫 |

#### 话术模板

| 字段 | 默认值 | 说明 |
|---|---|---|
| `disabled_template` | `打劫功能暂未开启。` | 功能关闭提示 |
| `self_target_template` | `不能打劫自己哦！` | 打劫自己提示 |
| `robber_not_bound_template` | `您尚未绑定网站ID，无法打劫。` | 打劫者未绑定提示 |
| `victim_not_bound_template` | `对方尚未绑定网站ID，无法打劫。` | 目标未绑定提示 |
| `invalid_quota_ratio_template` | `打劫失败：额度展示比例配置无效。` | 比例配置无效提示 |
| `balance_unavailable_template` | `打劫失败：暂时无法读取双方余额。` | 余额读取失败提示 |
| `victim_balance_empty_template` | `对方余额不足，无从下手！` | 目标余额不足提示 |
| `api_update_failed_template` | `打劫结算失败，请稍后再试。` | 远端结算失败提示 |
| `rollback_failed_template` | `打劫结算异常，资金状态未知，请联系管理员核查。` | 回滚失败提示 |
| `cooldown_template` | `打劫冷却中，请 {wait_seconds} 秒后再试。` | 冷却提示模板 |
| `wanted_template` | `您正在被通缉，请 {wait_seconds} 秒后再试。` | 通缉提示模板 |
| `failed_template` | `打劫失败！您赔付给对方 {display_amount:.2f} 额度，并被通缉 {wanted_seconds} 秒。` | 失败提示模板 |
| `success_template` | `打劫得手！\n获得 {display_amount:.2f} 额度！\n当前总额度为 {display_total:.2f}。` | 成功提示模板 |
| `success_doubled_template` | `打劫双倍得手！\n获得 {display_amount:.2f} 额度！\n当前总额度为 {display_total:.2f}。` | 双倍成功提示模板 |
| `success_balance_unknown_template` | `打劫得手！获得 {display_amount:.2f} 额度，但暂时无法读取最新余额。` | 成功但余额未知模板 |
| `success_doubled_balance_unknown_template` | `打劫双倍得手！获得 {display_amount:.2f} 额度，但暂时无法读取最新余额。` | 双倍成功但余额未知模板 |
| `unexpected_status_template` | `打劫处理异常: {status}` | 未知状态模板 |
| `user_info_unavailable_template` | `无法获取您的用户信息。` | 用户信息缺失提示 |
| `invalid_target_template` | `格式错误，请使用 /打劫 @用户名 或 /打劫 用户ID。` | 目标格式错误提示 |

**打劫模板可用变量**：

| 变量 | 含义 |
|---|---|
| `{wait_seconds}` | 冷却 / 通缉剩余秒数 |
| `{display_amount:.2f}` | 转移（或赔付）的显示额度 |
| `{display_total:.2f}` | 打劫者到账后的总显示额度 |
| `{wanted_seconds}` | 通缉秒数 |
| `{status}` | 内部状态码 |

> 模板字段缺失或格式错误时，插件会回退到内置中文文案，保证命令始终有回复。

---

### 8.7 私聊高级开关（`pm`）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enable_all_pm` | `true` | 是否允许所有用户在**私聊**中使用指令。为 `false` 时，私聊指令仅对 `permission.admin_users` 中的管理员放行 |

---

### 8.8 邮箱验证绑定（`email`）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `true` | 是否启用邮箱验证绑定。为 `false` 时 `/绑定` 回退为旧版一次性绑定，便于未配置 SMTP 的存量部署平滑过渡 |
| `smtp_host` | 空 | SMTP 服务器地址（如 `smtp.qq.com`）。**必填**，与 `smtp_user`、`smtp_password` 任一为空时无法发信 |
| `smtp_port` | `465` | SMTP 端口。默认 `465`，走 `SMTP_SSL`（隐式 TLS） |
| `smtp_user` | 空 | SMTP 登录账号（发件邮箱） |
| `smtp_password` | 空 | SMTP 授权码 / 密码 |
| `ignore_ssl` | `true` | 是否忽略 SSL 证书校验。自签名证书 / 内网环境开启；公网正式 SMTP 建议关闭以防范中间人窃取账号与授权码 |
| `code_ttl_seconds` | `300` | 验证码有效期（秒），过期需重新发起 `/绑定` |
| `mail_subject_template` | `绑定验证码` | 邮件主题模板，可用变量 `{code}`、`{ttl_seconds}` |
| `mail_body_template` | `您的绑定验证码是 {code}，请在 {ttl_seconds} 秒内使用 /绑定验证 <验证码> 完成绑定。` | 邮件正文模板，可用变量 `{code}`、`{ttl_seconds}` |

> 发信使用 Python 标准库 `smtplib` + `SMTP_SSL`（465 端口），在后台线程（`asyncio.to_thread`）执行并设置 10 秒超时，不会阻塞 MaiBot 事件循环。模板字段缺失或格式错误时自动回退默认文案。
> ⚠️ `smtp_password` 为明文敏感配置，与 API 令牌同级，请勿提交到仓库；`config.toml`、`.env`、`*.db` 已在 `.gitignore` 排除。

---

## 9. 权限模型

权限检查由 `_permission_allowed()` 统一处理，顺序如下：

1. **私聊消息**（`is_private_message` 或 `type=private`）：
   - `pm.enable_all_pm = true` → 放行。
   - 否则仅当发送者用户名在 `permission.admin_users` 中才放行。
2. **群聊 / 频道消息**：
   - `mode = whitelist`：仅 `channel_id` 在白名单中放行。
   - `mode = blacklist`：`channel_id` 不在黑名单中放行。
   - `mode = all`：全部放行。
3. **管理员命令**（`/查询` `/解绑` `/调整余额`）：在通过上述基础检查后，**额外**要求发送者用户名在 `permission.admin_users` 中。

---

## 10. 数据库与数据存储

插件使用 SQLite，数据库文件位于 MaiBot 数据目录：

```text
<MaiBot data_dir>/newapi_data.db
```

启用 WAL 模式以支持并发读写。

### 表结构

**`newapi_bindings`** — 绑定关系表：

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `qq_id` | 平台用户 ID（唯一） |
| `website_user_id` | NewAPI 网站用户 ID（唯一索引） |
| `binding_time` | 绑定时间 |
| `last_check_in_time` | 最近一次签到时间 |

**`newapi_robbery_states`** — 打劫状态表：

| 字段 | 说明 |
|---|---|
| `qq_id` | 打劫者用户 ID（主键） |
| `cooldown_until` | 成功冷却截止时间 |
| `wanted_until` | 通缉截止时间 |

**`newapi_binding_verifications`** — 邮箱绑定验证码表：

| 字段 | 说明 |
|---|---|
| `qq_id` | 平台用户 ID（主键，一用户仅一条待验证记录，重复申请会覆盖） |
| `website_user_id` | 待绑定的 NewAPI 网站用户 ID |
| `code` | 6 位数字验证码（`secrets` 密码学安全随机生成） |
| `expires_at` | 验证码过期时间（UTC ISO 字符串） |
| `attempts` | 连续错误验证码次数，达到 5 次后记录被删除（防暴力枚举） |
| `created_at` | 记录创建时间 |

### 数据迁移

直接替换旧版插件目录、保留同一 `data_dir` 时，新版会自动迁移：

- 保留已有绑定数据。
- 自动补充缺失的 `last_check_in_time` 列。
- 自动创建 `newapi_robbery_states` 表。
- 自动创建 `newapi_binding_verifications` 表（幂等建表，老库启动时自动补建，无需 ALTER）。
- 自动为 `website_user_id` 建立唯一索引。

**需要人工处理**：
- 旧库存在重复 `website_user_id`：插件会**拒绝启动**并列出重复 ID，需要先备份数据库、清理重复绑定后重启。
- 旧表缺失核心列（`qq_id`、`website_user_id`）：无法安全自动修复，建议手工重建。

> 💾 **升级前建议先备份 `newapi_data.db`**。

---

## 11. 文件结构说明

```text
maibot_plugin_newapi/
├── _manifest.json        # 插件清单：声明插件 ID、版本、宿主/SDK 兼容范围、依赖、能力
├── plugin.py             # 插件入口：配置模型、WebUI 元数据、生命周期、全部 @Command 命令
├── newapi_utils.py       # 核心逻辑：SQLite、NewAPI 请求、额度换算、签到/打劫/调额/绑定/解绑
├── test_newapi_utils.py  # 核心回归测试（unittest，覆盖签到并发、打劫资金流、迁移等）
├── README.md             # 本文档
├── CLAUDE.md             # 面向 Claude Code / AI 代理的开发指引
├── requirements.txt      # Python 依赖声明（maibot-plugin-sdk、httpx）
├── config.toml           # 运行时配置（可选，已 gitignore）
├── .env                  # 环境变量配置（可选，已 gitignore）
└── .gitignore            # Git 忽略规则
```

### 各文件职责

**`_manifest.json`**
MaiBot 发现和加载插件的入口描述：插件 ID `future-404.maibot-plugin-newapi`、版本 `2.6.0`、MaiBot `>= 1.1.3`、SDK `>= 2.0.0`、声明 `httpx` 依赖和 `send.text` 能力。修改版本范围时要考虑加载兼容性。

**`plugin.py`**
- 定义 8 个 `PluginConfigBase` 配置段（`plugin`、`api`、`permission`、`binding`、`check_in`、`robbery`、`pm`、`email`）。
- 实现 `on_load` / `on_unload` / `on_config_update` 生命周期（配置热更新回调签名 `(scope, config_data, version)`）。
- 实现 8 个 `@Command` 命令（`/查询余额`、`/绑定`、`/绑定验证`、`/签到`、`/打劫`、管理员 `/查询`、`/解绑`、`/调整余额`），以及权限判断、用户名/用户 ID/提及/流 ID 提取等工具方法。
- 所有命令回复统一走 `_send_and_return(text, stream_id)`。

**`newapi_utils.py`**
- `NewApiCore`：负责 SQLite、NewAPI HTTP 请求和额度业务。
- 关键方法：`perform_check_in()`（签到）、`perform_robbery()`（打劫）、`adjust_balance_by_identifier()`（管理员调额）、`bind` / `purge_user_binding` / `revert_user_group`（绑定/解绑）、`add_api_user_quota` / `change_api_user_quota`（管理员加减额）。
- 邮箱验证绑定：`generate_code()`（`secrets` 生成 6 位验证码）、`set_binding_verification()` / `get_binding_verification()` / `verify_binding_code()` / `clear_binding_verification()`（待验证记录写入/读取/校验/清理，校验含错误计数锁定与过期清除）、`send_verification_email()` / `_send_verification_email_sync()`（SMTP 发信，后台线程执行）。

**`test_newapi_utils.py`**
不依赖 MaiBot 宿主的回归测试，用临时 SQLite 和 mock HTTP 验证核心逻辑，包括签到并发防重、打劫资金流与回滚、旧库迁移、唯一约束等。

---

## 12. 额度换算与 NewAPI 接口说明

### 额度换算

- NewAPI 的 `quota` 是**原始整数额度**。
- 显示额度 = `quota / binding.quota_display_ratio`。
- 配置里的签到、打劫、调额数值都是**显示额度**，写回 API 前必须乘以 `quota_display_ratio` 并取整。

### 使用的 NewAPI 接口

| 接口 | 用途 |
|---|---|
| `GET /api/user/{id}` | 读取网站用户资料（余额、分组） |
| `PUT /api/user/` | 更新用户分组（绑定/解绑时） |
| `POST /api/user/manage` | **管理员原子调额**：`action: add_quota` + `mode: add/subtract` + `value: 原始额度` |

所有请求使用 `Authorization: Bearer <管理员 PAT>`。**不依赖已废弃的 `New-Api-User` 头，不生成兑换码，不使用 `/api/user/topup`。**

> ⚠️ 上游 NewAPI 的 `subtract` 不会自动阻止负余额。插件在扣款前会先读取余额并限制扣款额，但无法完全消除与并发消费竞争时的负余额风险。这是 NewAPI 接口本身的限制。

---

## 13. 开发与验证

### 安装依赖

```bash
pip install -r requirements.txt
```

### 语法检查

```bash
python -m compileall plugin.py newapi_utils.py
```

### 回归测试

```bash
python -m unittest -v test_newapi_utils.py
```

### 端到端验证建议

插件依赖 MaiBot 的 Host/Runner 运行环境，最终验证应在**非生产** NewAPI 测试账户中完成：

1. 配置管理员 PAT 和测试网站用户。
2. 执行 `/绑定`、`/签到`、`/打劫`、`/调整余额`。
3. 确认管理员账户余额不变、绑定网站用户余额按预期增减。
4. 在 NewAPI 管理日志中检查 `add_quota` 操作。

---

## 14. 常见问题与注意事项

**1. 插件加载失败，日志提示 `[plugin] 配置节` 缺失？**
`plugin.config_version` 是 MaiBot 必需契约，配置中必须保留 `plugin` 段，不要删除。

**2. 管理员命令一直提示权限不足？**
`permission.admin_users` 现在使用**用户名**。请确认填入的是发送者在平台上的用户名，而不是数字 ID。

**3. 签到/打劫提示"无法更新 NewAPI 系统额度"？**
检查 `api_base_url`、`api_access_token` 是否正确，管理员 PAT 是否对目标网站用户有管理权限（普通管理员不能管理同级或更高角色）。

**4. 打劫显示"资金状态未知，请联系管理员"？**
说明跨账户第二步转账与补偿都失败，存在资金不一致风险，需要管理员到 NewAPI 后台核查双方账户额度。

**5. 升级后插件拒绝启动，提示重复网站 ID？**
旧数据库存在一个网站 ID 被多个用户绑定的历史数据。备份数据库后，删除/合并重复绑定记录再启动。

**6. Discord 上能用 `/打劫 @用户名` 吗？**
可以。当前插件命令基于**文本正则匹配**（MaiBot 的 Discord 适配器把消息文本交给宿主，由 `command_pattern` 正则命中）。原生 Discord 用户提及会同时保留为结构化 `mention` 消息段，目标 ID 位于 `raw_message[*].data.users[*].user_id`，因此插件会优先使用原生 ID 定位目标；对旧版适配器或纯文本输入，则回退为绑定时记录的 `@用户名` 反向查表。`/解绑`、`/查询`、`/调整余额` 同理。MaiBot 当前不注册 Discord 原生斜杠命令，因此这些命令不会出现在 Discord 的命令菜单里。

**7. `/绑定` 提示"验证码发送失败"？**
SMTP 未配置或连接失败。请在 `email` 配置段填写 `smtp_host` / `smtp_user` / `smtp_password`（QQ / 163 等邮箱需使用**授权码**而非登录密码），并确认端口与加密方式匹配（默认 `465` + `SMTP_SSL`）。

**8. 收不到绑定验证码邮件？**
先检查垃圾邮件箱。确认 `smtp_user` 填的是发件邮箱、且该邮箱已开启 SMTP 服务并取得授权码；再确认部署环境能连通 SMTP 服务器的 `465` 端口。测试域名 / 新域名邮箱容易被服务商拦截，可先用真实发件账号自测。

**9. 什么是 `ignore_ssl`？**
`SMTP_SSL` 默认会校验服务器证书，自签名证书环境下会握手失败。开启 `ignore_ssl` 可跳过证书校验，但存在中间人窃取 SMTP 账号 / 授权码的风险，仅建议在自签名 / 内网环境开启。

**10. 为什么机器人回复前会带 `@用户名`？**
这是插件的默认行为：如果消息中包含发送者 ID，回复会优先使用 Discord 原生提及格式（`<@用户ID>`）；只有无法取得 ID 时才回退为文本 `@用户名`。如果无法从消息中提取用户名，则不发 `@` 前缀。

---

## 15. 开源协议

MIT License
