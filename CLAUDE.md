# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## 项目概述

这是 MaiBot 的 `newapi_suite` 管理插件（插件 ID `future-404.maibot-plugin-newapi`），用于把平台用户 ID 与 NewAPI 网站用户绑定，并提供余额查询、每日签到和管理员余额调整/解绑工具。

插件使用 MaiBot >= 1.1.3 的 Host/Runner 架构和 `maibot-plugin-sdk >= 2.0.0`。插件在独立 Runner 进程中运行，通过 SDK 的 `self.ctx` 与宿主通信。源码不得导入 MaiBot 的 `src.*`，只使用 `maibot_sdk` 及插件上下文能力。

## 开发与验证

仓库没有构建、lint 或测试配置，也没有可独立运行的入口。依赖项为：

```bash
pip install -r requirements.txt
```

其中 `requirements.txt` 声明 `maibot-plugin-sdk>=2.0.0` 和 `httpx>=0.24.0`；安装到 MaiBot 时，`_manifest.json` 也会让 Runner 自动安装 `httpx`。

可以用下面的命令做基础语法检查，但它不替代 MaiBot 集成验证：

```bash
python -m compileall plugin.py newapi_utils.py
```

核心回归测试在 `test_newapi_utils.py`（`unittest` + `IsolatedAsyncioTestCase`，用临时 SQLite 与替换 `api_request` 的 mock 验证，不依赖 MaiBot 宿主）：

```bash
# 运行全部测试
python -m unittest -v test_newapi_utils.py
# 运行单个测试（例如打劫随机额度）
python -m unittest test_newapi_utils.NewApiCoreTests.test_robbery_uses_random_quota_range
```

实际验证方式是把整个目录放到 MaiBot 的 `plugins/` 目录后启动 MaiBot，查看插件日志（`newapi_suite`）。插件无法脱离 MaiBot 环境直接运行，因为 `plugin.py` 依赖 `maibot_sdk` 和宿主上下文。配置可在 WebUI 插件配置页修改，或使用运行时生成的 `config.toml`；配置更新通过 `on_config_update` 动态刷新 API 连接。

## 架构

- **`plugin.py`** 是插件入口。
  - `NewApiSuiteConfig` 由 `PluginConfigBase` 的嵌套配置段组成：`plugin`、`api`、`permission`、`binding`、`check_in`、`robbery`、`pm`、`email`。`plugin.config_version` 必须保留，用于 MaiBot 配置文件解析。
  - `NewApiSuitePlugin.on_load()` 从 `self.ctx` 读取配置和数据目录，创建并初始化 `NewApiCore`；`on_config_update()` 更新配置并调用核心的 `refresh_config()`。
  - 用户和管理员指令通过 SDK 的 `@Command` 声明。命令处理器从 `kwargs` 获取 `message`、`stream_id` 和 `matched_groups`，通过 `self.ctx.send.text(text, stream_id)` 发送回复，并返回 `(success, response, weight)`。
  - `_extract_user_id()`、`_extract_username()`、`_extract_mention()` 和 `_extract_stream_id()` 兼容多种 MaiBot/平台消息字典结构。权限统一由 `_permission_allowed()` 和 `_is_admin()` 检查：普通命令受频道模式和私聊开关约束，管理员命令还要求发送者的用户名位于 `permission.admin_users`（用用户名而非 ID，避免 ID 作为大整数被配置系统丢失精度）。`_extract_mention()` 按消息段的 `at`/`mention` 类型解析 `id`/`target_id`/`user_id`/`qq` 等键，也支持 Discord 消息对象顶层的 `mentions` 数组，最后用正则兜底 `<@!?id>` 与 `[CQ:at,qq=id]`；注意不要误把角色 `<@&id>`、频道 `<#id>` 识别为用户。
  - 命令的目标解析统一走 `_resolve_target()`（异步）：依次尝试 `_extract_mention()`、纯数字 `matched_groups["identifier"]`，最后若以 `@` 开头则去掉 `@` 按 `newapi_bindings.qq_username` 查绑定记录返回其 `qq_id`。这是因为某些平台适配器（如 litroenade/MaiBot-Discord-Adapter）会把消息中的 `<@ID>` 替换为 `@用户名` 文本并丢弃数字 ID，插件只能在绑定时记录用户名再反向查表。绑定流程 `_perform_binding_ritual()` 会用 `_extract_username()` 保存用户名到 `qq_username` 列。
  - 当前命令为：`/查询余额`、`/绑定 <网站ID>`（两步绑定第一步，发邮箱验证码）、`/绑定验证 <验证码>`（两步绑定第二步）、`/签到`、`/打劫 <ID或@用户>`、管理员 `/查询 <ID或@用户>`、管理员 `/解绑 <ID或@用户>`、管理员 `/调整余额 <ID或@用户> <数额>`。

- **`newapi_utils.py`** 提供 `NewApiCore`，负责本地数据、NewAPI HTTP 请求和额度业务。
  - SQLite 数据库默认为 `self.ctx.paths.data_dir / "newapi_data.db"`，建表时启用 WAL。核心表 `newapi_bindings` 保存平台用户 ID、网站用户 ID、绑定时间、最近签到时间和绑定时的用户名（`qq_username`，用于按用户名反向解析目标）；`newapi_binding_verifications` 保存邮箱绑定待验证记录（`qq_id` 主键、`website_user_id`、`code`、`expires_at`、`attempts` 失败计数），由 `_ensure_tables_exist_sync()` 幂等建表，老库启动时自动补建（含 `attempts` 列迁移）。
  - `execute_query()` 通过 `asyncio.to_thread()` 执行同步 SQLite 操作，查询结果转换为字典；不要在命令处理器中直接操作数据库。
  - `api_request()` 仅使用管理员 PAT 的 `Authorization: Bearer ...` 请求头访问 NewAPI，不使用已废弃的 `New-Api-User` 头。API 配置优先读取 `plugin.config.api`，缺失时兼容插件目录下的 `config.toml` `[api]` 段和 `.env`（`API_BASE_URL`、`API_ACCESS_TOKEN`）。不要把令牌写入源码或提交内容。
  - NewAPI 的 `quota` 是原始整数额度；用户可见额度使用 `quota / binding.quota_display_ratio`，配置中的签到、打劫和调整数值均为可见额度，写回 API 前必须乘以该比例。展示比例必须大于零。
  - `change_api_user_quota(user_id, raw_amount, mode)` 是管理员调额入口，走 `POST /api/user/manage` 的 `action: add_quota`，`mode` 为 `add`/`subtract`；`add_api_user_quota()` 是它的 `add` 便捷包装。上游 `subtract` 不会阻止负余额，插件在扣款前会读取余额并限制扣款额，但不能消除并发消费导致的负余额风险。
  - `perform_check_in()` 使用 SQLite 事务原子抢占当天签到资格，计算随机/翻倍/首次奖励后，通过管理员 `add` 操作将额度直接加入绑定网站用户。远端调额失败时仅回滚本次占位；余额读取失败不影响已成功的入账。
  - `perform_robbery()` 使用 `newapi_robbery_states` 的原子占位记录成功冷却和失败通缉。规则全部来自 `RobberySettings`：成功概率、双倍概率、成功转移额度随机范围（`min_display_quota`/`max_display_quota`，兼容旧字段 `base_display_quota`）、失败赔付比例与上限、冷却与通缉秒数。成功时从目标账户 `subtract` 扣款并给打劫者 `add` 加款；失败时从打劫者账户赔付目标。跨账户第二步失败时尝试反向补偿；若第二步网络结果未知则**不**盲目补偿，避免远端已入账导致重复增发，返回不确定状态供审计。
  - `adjust_balance_by_identifier()` 当前只接受正额度，通过同一管理员 `add` 操作完成加额；负数或零会返回本地无效额度状态。不要将它误认为支持扣款或双向资金转移。
  - 邮箱验证绑定：`generate_code()` 用 `secrets` 生成 `length` 位纯数字验证码（密码学安全随机）；`set_binding_verification()` 以 `BEGIN IMMEDIATE` + `ON CONFLICT(qq_id) DO UPDATE` 覆盖写入待验证记录（`expires_at = utcnow + ttl`）；`verify_binding_code()` 按 存在/过期/匹配 返回 `NOT_FOUND`/`EXPIRED`/`INVALID`/`SUCCESS`——错误尝试会累计到 `attempts` 列，连续 5 次错误或过期时删除记录并返回 `LOCKED`/`EXPIRED`，需重新 `/绑定` 获取新码（防暴力枚举）；`send_verification_email()` 经 `asyncio.to_thread` 调 `_send_verification_email_sync()`，用标准库 `smtplib.SMTP_SSL`（默认 465、timeout 10s）发信，模板渲染失败回退默认文案，`ignore_ssl` 时用 `ssl._create_unverified_context()`。

## 关键约束

- 配置访问使用强类型对象，例如 `self.config.api`、`self.config.permission`、`self.config.binding`、`self.config.check_in`、`self.config.robbery` 和 `self.config.email`，不要恢复旧版扁平 `config_schema` 或旧 dispatcher 写法。
- 数据库和配置属于运行时数据：`*.db`、`.env`、`config.toml` 已被 `.gitignore` 排除，不参与插件发布。
- 修改 `_manifest.json` 的宿主版本或 SDK 版本范围时要同步考虑 MaiBot 插件加载兼容性。当前清单是 `manifest_version: 2`、MaiBot `1.1.3` 起、SDK `2.0.0` 起，插件能力声明为 `send.text`。MaiBot 1.1.3 实际随附 SDK 版本应以宿主为准，配置热更新回调签名为 `(scope, config_data, version)`。
- 源码注释和用户可见文案使用中文；新增配置字段应直接加入 `NewApiSuiteConfig` 对应的配置段，并考虑 WebUI 字段元数据（`__ui_label__`、`__ui_icon__`、`__ui_order__`）。打劫与签到结果文案支持模板变量，用户可见行为以 `README.md` 为准；修改命令或配置语义后应同步更新 README 与 `test_newapi_utils.py`。

## 安装配置要点

将仓库目录放入 MaiBot 的 `plugins/` 后启动即可自动发现。至少需要配置 NewAPI 基础 URL 和具备管理权限的 API 访问令牌；若要启用插件管理员指令，还需在权限设置中配置允许的管理员用户名（`permission.admin_users`，使用用户名而非 ID 避免精度丢失）。若启用邮箱验证绑定（默认开启），还需在 `email` 配置段填写 SMTP 服务器、端口（默认 465）、账号、授权码；`ignore_ssl` 默认开启，用于自签名证书/测试环境，生产公网建议关闭。主要业务配置包括权限模式（`all`、`whitelist`、`blacklist`）、绑定后/解绑后的用户组、额度展示比例、签到奖励规则、打劫规则（成功/双倍概率、随机转移额度范围、失败赔付、冷却与通缉秒数）和私聊开关。每个配置项的完整说明见 `README.md`。
