# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是 MaiBot 的插件（`newapi_suite`，插件 ID `future-404.maibot-plugin-newapi`），为用户提供 NewAPI 网站的用户绑定、余额查询、每日签到和"打劫"娱乐功能。

插件基于**新版 Host/Runner 插件架构**（`maibot-plugin-sdk`，import 名 `maibot_sdk`）：插件运行在独立子进程（Runner）中，通过 msgpack RPC 与 MaiBot 主进程通信。**插件代码不得 import `src.*`**，只能通过 `maibot_sdk` 及其 `self.ctx` 能力代理访问宿主能力。

## 运行与开发

没有构建、lint 或测试体系。运行依赖：

- MaiBot >= 1.1.3（新版插件架构）
- `maibot-plugin-sdk`（`pip install maibot-plugin-sdk`）
- `httpx`（在 `_manifest.json` 的 `dependencies` 中声明，Runner 自动安装）

安装：把整个目录放入 MaiBot 的 `plugins/` 文件夹，启动 MaiBot 即自动加载。开发时无法脱离 MaiBot 环境直接运行；改动通过日志（logger 名 `newapi_suite` / `newapi_heist`）在 MaiBot 内验证。

## 架构

- **`plugin.py`** — 入口。`NewApiSuitePlugin(MaiBotPlugin)`：
  - `config_model = NewApiSuiteConfig`（`PluginConfigBase` 嵌套模型，定义全部配置与 WebUI Schema）
  - 生命周期：`on_load()` 初始化 `NewApiCore` 与 `HeistLogic`；`on_config_update(scope="self")` 调用 `core.refresh_config()`
  - 全部命令用 `@Command(name, pattern=...)` 声明（`cmd_*` 方法），处理函数从 `**kwargs` 取 `stream_id` / `matched_groups` / `message`，返回三元组 `(success, response, weight)`。命令命中即执行，不再触发 LLM 回复（这是新版 `@Command` 的天然行为，替代了旧版 stealth dispatcher）
  - `message` 是 dict，字段与旧版 `MaiMessages` 兼容：`user_info.user_id`、`message_info.user_info.user_id`、`message_base_info.group_id`、`message_segments[]`（at 段取 `data.user_id` / `data.target_user_id`）。`plugin.py` 提供了 `_extract_user_id` / `_extract_mention` / `_is_group_message` 等兼容提取辅助
  - 发送统一走 `self.ctx.send.text(text, stream_id)`，`stream_id` 直接来自 `kwargs`
- **`newapi_utils.py`** — `NewApiCore` 数据与 API 层。SQLite（WAL 模式）数据库文件位于 `self.ctx.paths.data_dir / "newapi_data.db"`；httpx 异步客户端访问 NewAPI（请求头 `Authorization` + `New-Api-User`）。
  - **额度表示**：NewAPI 返回的 `quota` 是整数原始值，显示额度 = `quota / binding.quota_display_ratio`（默认 500000）。配置中所有数值均为"显示额度"，代码内乘回比例
  - **签到的防刷设计**：`perform_check_in` 刻意"先本地写 `last_check_in_time` 锁定、后调 API 发奖"。即使 API 挂了用户也无法重复签到，安全优先于体验
  - **资金转移**：`_transfer_quota` 采用"双向确认"（先扣款后加款），加款失败时 3 次重试回滚，仍失败则写入 `pending_api_tasks` 表待人工补偿。任何改动额度流程务必沿用这一补偿机制
  - API 连接配置从 `plugin.config.api`（config_model）读取；若为空，回退解析插件目录的 `.env`（`API_BASE_URL` / `API_ACCESS_TOKEN` / `API_ADMIN_USER_ID`），兼容旧版部署
- **`heist_logic.py`** — `HeistLogic` 打劫小游戏。`execute_heist` 分三步：`_validate_heist_conditions`（启用开关、绑定、冷却、每日发起/被劫上限、自劫检查）→ `_determine_heist_outcome`（失败/成功/暴击判定）→ `_execute_heist_transfer`（走 `core.transfer_display_quota` 划转并记录 `daily_heist_log`）。暴击时先全额转移 `allow_partial=True`，再用"实际获得 > 基础额度"判定最终是否算暴击

## 需要注意的点

- **配置访问**：所有配置通过强类型 `self.plugin.config.xxx`（如 `config.binding.quota_display_ratio`、`config.check_in.enabled`）读取，字段名与旧版 `config_schema` 的 section 一致（`permission_settings`→`permission`、`check_in_settings`→`check_in`、`heist_settings`→`heist`）。新增的 `api` section 存 API 密钥
- **权限控制**：`permission.admin_list`（管理员）、`permission.allowed_groups`（允许频道，留空全放行）、`permission.enable_private_chat`（私聊开关），在 `plugin.py` 的 `_permission_allowed` / `_is_admin` 中统一校验
- **配置变更**：新增配置字段时在 `plugin.py` 的 `PluginConfigBase` 中声明即可，Runner 会自动补齐默认值；数据库建表在 `NewApiCore._ensure_tables_exist_sync`
- `_manifest.json` 为 `manifest_version: 2`，`host_application.min_version` 与 `sdk` 区间决定了插件能在哪些 MaiBot 版本加载，升级 SDK 大版本时需同步调整
- `config.toml`、`.env`、`*.db`、`docs/`、`sdk.zip`、`sdk_src/` 为运行时生成物或调研产物，均不参与插件运行
- 源码注释与用户可见文案均为中文，新增内容请保持一致
