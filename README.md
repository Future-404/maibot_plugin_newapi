# NewAPI Suite Plugin for MaiBot

集成了核心用户管理与娱乐功能的 NewAPI 插件套件，专为 MaiBot (Discord) 环境优化移植。

## 🌟 功能特性

- **核心绑定**：支持将 Discord 账号与 NewAPI 网站 ID 绑定，自动同步用户组。
- **余额查询**：用户可随时通过 `/查询余额` 查看关联账号的当前额度。
- **每日签到**：内置签到系统，支持配置随机奖励、双倍概率及首次签到礼包。
- **打劫互动**：趣味娱乐功能，用户可以对 @提及 的目标发起打劫，赢取或赔付额度。
- **管理工具**：
  - `/查询 [@用户/ID]`：智能识别目标并显示绑定详情。
  - `/解绑 [@用户/ID]`：强制解除账号绑定并自动恢复网站用户组。
  - `/调整余额 [@用户/ID] [数额]`：手动增减用户额度。
- **深度优化**：
  - **消息拦截**：指令触发后自动拦截，避免触发冗余的 LLM 回复，节省 Token。
  - **智能识别**：所有命令均支持通过 Discord `@提及` 操作。
  - **本地存储**：基于 SQLite，无需配置额外的数据库服务。

## 🚀 安装指南

1. 将 `maibot_plugin_newapi` 目录放入 MaiBot 的 `plugins` 文件夹。
2. 在插件目录下创建 `.env` 文件，配置你的 API 信息：
   ```env
   API_BASE_URL=http://your-api-domain:port
   API_ACCESS_TOKEN=your_token
   API_ADMIN_USER_ID=1
   ```
3. 在容器内安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
4. 重启 MaiBot 即可自动加载并生成 `config.toml` 配置文件。

## ⚙️ 配置说明

插件启动后会生成 `config.toml`，你可以通过 WebUI 或手动编辑该文件来调整：
- 签到奖励数值
- 打劫成功率及冷却时间
- 提示词模版（支持自定义各种交互文案）

## 📄 开源协议

MIT License
