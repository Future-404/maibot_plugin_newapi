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

实际验证方式是把整个目录放到 MaiBot 的 `plugins/` 目录后启动 MaiBot，查看插件日志（`newapi_suite`）。插件无法脱离 MaiBot 环境直接运行，因为 `plugin.py` 依赖 `maibot_sdk` 和宿主上下文。配置可在 WebUI 插件配置页修改，或使用运行时生成的 `config.toml`；配置更新通过 `on_config_update` 动态刷新 API 连接。

## 架构

- **`plugin.py`** 是插件入口。
  - `NewApiSuiteConfig` 由 `PluginConfigBase` 的嵌套配置段组成：`plugin`、`api`、`permission`、`binding`、`check_in`、`pm`。`plugin.config_version` 必须保留，用于 MaiBot 配置文件解析。
  - `NewApiSuitePlugin.on_load()` 从 `self.ctx` 读取配置和数据目录，创建并初始化 `NewApiCore`；`on_config_update()` 更新配置并调用核心的 `refresh_config()`。
  - 用户和管理员指令通过 SDK 的 `@Command` 声明。命令处理器从 `kwargs` 获取 `message`、`stream_id` 和 `matched_groups`，通过 `self.ctx.send.text(text, stream_id)` 发送回复，并返回 `(success, response, weight)`。
  - `_extract_user_id()`、`_extract_mention()` 和 `_extract_stream_id()` 兼容多种 MaiBot/平台消息字典结构。权限统一由 `_permission_allowed()` 和 `_is_admin()` 检查：普通命令受频道模式和私聊开关约束，管理员命令还要求发送者位于 `permission.admin_users`。
  - 当前命令为：`/查询余额`、`/绑定 <网站ID>`、`/签到`、管理员 `/查询 <ID或@用户>`、管理员 `/解绑 <ID或@用户>`、管理员 `/调整余额 <ID或@用户> <数额>`。

- **`newapi_utils.py`** 提供 `NewApiCore`，负责本地数据、NewAPI HTTP 请求和额度业务。
  - SQLite 数据库默认为 `self.ctx.paths.data_dir / "newapi_data.db"`，建表时启用 WAL。核心表 `newapi_bindings` 保存平台用户 ID、网站用户 ID、绑定时间和最近签到时间。
  - `execute_query()` 通过 `asyncio.to_thread()` 执行同步 SQLite 操作，查询结果转换为字典；不要在命令处理器中直接操作数据库。
  - `api_request()` 仅使用管理员 PAT 的 `Authorization: Bearer ...` 请求头访问 NewAPI。API 配置优先读取 `plugin.config.api`，缺失时兼容插件目录下的 `config.toml` `[api]` 段和 `.env`（`API_BASE_URL`、`API_ACCESS_TOKEN`）。不要把令牌写入源码或提交内容。
  - NewAPI 的 `quota` 是原始整数额度；用户可见额度使用 `quota / binding.quota_display_ratio`，配置中的签到和调整数值均为可见额度，写回 API 前必须乘以该比例。展示比例必须大于零。
  - `perform_check_in()` 使用 SQLite 事务原子抢占当天签到资格，计算随机/翻倍/首次奖励后，通过管理员 `POST /api/user/manage` 的 `add_quota` 操作将额度直接加入绑定网站用户。远端调额失败时仅回滚本次占位；余额读取失败不影响已成功的入账。
  - `adjust_balance_by_identifier()` 当前只接受正额度，通过同一管理员 `add_quota` 操作完成加额；负数或零会返回本地无效额度状态。不要将它误认为支持扣款或双向资金转移。

## 关键约束

- 配置访问使用强类型对象，例如 `self.config.api`、`self.config.permission`、`self.config.binding` 和 `self.config.check_in`，不要恢复旧版扁平 `config_schema` 或旧 dispatcher 写法。
- 数据库和配置属于运行时数据：`*.db`、`.env`、`config.toml` 已被 `.gitignore` 排除，不参与插件发布。
- 修改 `_manifest.json` 的宿主版本或 SDK 版本范围时要同步考虑 MaiBot 插件加载兼容性。当前清单是 `manifest_version: 2`、MaiBot `1.1.3` 起、SDK `2.0.0` 起，插件能力声明为 `send.text`。MaiBot 1.1.3 实际随附 SDK 版本应以宿主为准，配置热更新回调签名为 `(scope, config_data, version)`。
- 源码注释和用户可见文案使用中文；新增配置字段应直接加入 `NewApiSuiteConfig` 对应的配置段，并考虑 WebUI 字段元数据。

## 安装配置要点

将仓库目录放入 MaiBot 的 `plugins/` 后启动即可自动发现。至少需要配置 NewAPI 基础 URL 和具备管理权限的 API 访问令牌；若要启用插件管理员指令，还需在权限设置中配置允许的 MaiBot 管理员 ID。主要业务配置包括权限模式（`all`、`whitelist`、`blacklist`）、绑定后/解绑后的用户组、额度展示比例、签到奖励规则和私聊开关。
