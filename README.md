# NewAPI Suite Plugin for MaiBot

集成了核心用户管理与真实发额度签到功能的 NewAPI 插件套件，专为 MaiBot 1.1.3+ SDK v2 架构打造。

## 功能特性

- **核心绑定**：支持将 Discord / QQ 账号与 NewAPI 网站 ID 绑定，自动同步用户组。
- **余额查询**：用户可随时通过 `/查询余额` 查看关联账号的当前额度。
- **真实签到**：基于【管理员动态发码 + 用户身份自动 TopUp 核销】机制，签到额度实时充入网站真余额，账目留存可追溯；支持配置随机奖励、双倍概率及首次签到礼包。
- **数据库防刷与回滚**：签到记录优先在 SQLite 本地锁定；若上游 API 网络出现故障，自动回滚签到状态，保障用户权益。
- **管理工具**：
  - `/查询 [@用户/ID]`：智能识别目标并显示绑定详情。
  - `/解绑 [@用户/ID]`：强制解除账号绑定并自动恢复网站用户组。
  - `/调整余额 [@用户/ID] [数额]`：手动增减用户额度。
- **本地存储**：基于 SQLite (开启 WAL 并发模式)，无缝维护用户映射。
- **消息拦截**：所有指令通过 MaiBot 新版 `@Command` 组件匹配触发，指令命中后拦截后续 AI 闲聊响应，节省 Token。

## 环境要求

- **MaiBot >= 1.1.3**（新版 Host/Runner 插件架构，`maibot_sdk` 插件 SDK）
- **maibot-plugin-sdk >= 2.0.0**

## 安装与配置

1. 将本目录放入 MaiBot 的 `plugins` 文件夹。
2. 启动 MaiBot，插件会被自动发现并加载。
3. 在 WebUI 插件配置页（或插件目录自动生成的 `config.toml`）修改 API 连接信息：
   - `api_base_url`：NewAPI 站点地址（如内部容器网桥 `http://172.17.0.1:3000` 或外部域名）
   - `api_access_token`：API 全限访问令牌
   - `api_admin_user_id`：管理员用户 ID Header (默认 `1`)
4. 保存后配置支持动态热重载。

## 目录结构

```
maibot_plugin_newapi/
├── _manifest.json   # 插件清单（manifest_version 2）
├── plugin.py        # 插件入口：配置模型、WebUI 元数据、生命周期、@Command 命令
├── newapi_utils.py  # NewAPI 核心：SQLite 存储、API 交互、卡密核销、事务回滚
└── config.toml      # 运行时配置文件（.gitignore）
```

## 开源协议

MIT License
