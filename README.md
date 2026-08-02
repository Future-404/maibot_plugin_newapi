# NewAPI Suite Plugin for MaiBot

集成了核心用户管理与娱乐功能的 NewAPI 插件套件，专为 MaiBot 环境优化移植。

## 功能特性

- **核心绑定**：支持将 Discord 账号与 NewAPI 网站 ID 绑定，自动同步用户组。
- **余额查询**：用户可随时通过 `/查询余额` 查看关联账号的当前额度。
- **每日签到**：内置签到系统，支持配置随机奖励、双倍概率及首次签到礼包。
- **打劫互动**：趣味娱乐功能，用户可以对 @提及 的目标发起打劫，赢取或赔付额度。
- **管理工具**：
  - `/查询 [@用户/ID]`：智能识别目标并显示绑定详情。
  - `/解绑 [@用户/ID]`：强制解除账号绑定并自动恢复网站用户组。
  - `/调整余额 [@用户/ID] [数额]`：手动增减用户额度。
- **本地存储**：基于 SQLite，无需配置额外的数据库服务。
- **消息拦截**：所有指令通过 MaiBot 新版 `@Command` 组件匹配触发，指令命中后不再触发冗余的 LLM 回复，节省 Token。

## 环境要求

- **MaiBot >= 1.1.3**（新版 Host/Runner 插件架构，`maibot_sdk` 插件 SDK）
- **maibot-plugin-sdk >= 2.0.0**（Runner 会自动安装，也可手动 `pip install maibot-plugin-sdk`）
- Python 依赖 `httpx` 已通过 `_manifest.json` 声明，Runner 会自动安装

## 安装指南

1. 将本目录放入 MaiBot 的 `plugins` 文件夹。
2. 启动 MaiBot，插件会被自动发现并加载，缺失的 `httpx` 依赖会自动安装。
3. 在 WebUI 插件配置页（或插件目录自动生成的 `config.toml`）填写 API 信息：
   - `api_base_url`：NewAPI 站点地址（如 `http://your-api-domain:port`）
   - `api_access_token`：API 访问令牌
   - `api_admin_user_id`：请求 API 时使用的管理员用户 ID
4. 保存后配置热重载，插件即可使用。

> **兼容旧版**：若配置中未填写 `api_base_url` / `api_access_token`，插件会回退读取插件目录下的 `.env` 文件（`API_BASE_URL`、`API_ACCESS_TOKEN`、`API_ADMIN_USER_ID`），方便从旧版本无缝迁移。

## 配置说明

通过 WebUI 或 `config.toml` 可调整以下分组配置：

- **连接设置**：API 站点地址、访问令牌、管理员用户 ID
- **权限控制**：管理员 ID 列表、允许生效的频道列表、私聊开关
- **核心绑定**：默认用户组、额度转换比例（显示额度 = quota / ratio，默认 500000）
- **签到功能**：奖励范围、双倍概率、新人礼包、提示词模板
- **打劫互动**：成功率、冷却时间、每日次数上限、提示词模板
- **可选通知**：绑定成功私信开关与模板
- <img width="1381" height="643" alt="image" src="https://github.com/user-attachments/assets/0cf00dfb-01a3-46aa-8871-043b3a8803bf" />


## 目录结构

```
maibot_plugin_newapi/
├── _manifest.json   # 插件清单（manifest_version 2）
├── plugin.py        # 插件入口：配置模型、生命周期、@Command 命令
├── newapi_utils.py  # NewAPI 核心：SQLite 存储、HTTP API、额度转移
├── heist_logic.py   # 打劫小游戏逻辑
└── config.toml      # 运行时生成（.gitignore）
```

## 开源协议

MIT License
