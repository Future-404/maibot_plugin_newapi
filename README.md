# NewAPI Suite Plugin for MaiBot

MaiBot 的 NewAPI 管理插件，提供网站账号绑定、余额查询、每日签到，以及管理员查询、解绑和增加额度。

## 功能

- 绑定 Discord / QQ 平台用户与 NewAPI 网站用户 ID，并同步网站用户组。
- 用户通过 `/查询余额` 查询绑定账户的真实余额。
- 用户通过 `/签到` 获得随机、翻倍或首次签到奖励。
- 用户通过 `/打劫 @用户` 进行可配置概率的余额转移；成功可能获得双倍额度，失败会按规则赔付对方并进入通缉状态。
- 签到、打劫和管理员加额都调用 NewAPI 的管理员原子调额接口 `POST /api/user/manage`。
- 本地 SQLite 使用 WAL，网站用户 ID 具有唯一性；签到采用原子占位防止并发重复领取。
- 管理员可使用 `/查询 [@用户/ID]`、`/解绑 [@用户/ID]`、`/调整余额 [@用户/ID] [正数]`。

## 环境要求

- MaiBot >= 1.1.3
- MaiBot 随附的 `maibot-plugin-sdk`（建议 >= 2.7.1）
- NewAPI 最新版，且配置的管理员 PAT 对目标网站用户拥有管理权限。

## 安装与配置

1. 将本目录放入 MaiBot 的 `plugins` 文件夹。
2. 启动 MaiBot，插件会被自动发现并加载。
3. 在 WebUI 插件配置页配置：
   - `api_base_url`：NewAPI 站点地址。
   - `api_access_token`：管理员 PAT 或访问令牌。
   - `binding_group`：绑定成功后授予的用户组。
   - `unbind_group`：解绑时恢复的用户组。
   - `quota_display_ratio`：显示额度到 NewAPI 原始整数额度的换算比例，必须大于零。
   - `robbery.enabled`：是否启用打劫。
   - `robbery.success_chance` / `double_chance`：成功概率与双倍概率。
   - `robbery.base_display_quota`：成功时的基础转移额度。
   - `robbery.cooldown_seconds` / `wanted_seconds`：成功冷却和失败通缉时间。
   - `robbery.failure_penalty_ratio` / `failure_penalty_max_display_quota`：失败时从打劫者余额赔付给对方的比例和上限。
   - 打劫结果文案：`robbery` 下的 `*_template` 字段可在 WebUI 中配置，覆盖功能关闭、绑定校验、余额不足、结算、冷却、通缉、成功及失败提示。
     - 可用变量：`{wait_seconds}`、`{display_amount:.2f}`、`{display_total:.2f}`、`{wanted_seconds}`、`{status}`。
     - 模板字段缺失或格式错误时，插件会使用内置中文文案，确保命令仍可回复。
4. 也可在插件目录的运行时 `config.toml` `[api]` 段或 `.env` 中设置 `API_BASE_URL`、`API_ACCESS_TOKEN`。WebUI 配置优先。

管理员 PAT 必须能够管理被绑定的网站用户；普通管理员不能管理同级或更高角色的账户。

## 绑定说明

`/绑定 <网站ID>` 保留为自助操作。它通过网站 ID 建立映射并调整该网站用户组，但聊天平台无法凭网站 ID 验证账户归属。请只在可信频道启用插件，或通过 `permission.mode`、白名单和管理员配置限制可用范围。

## 开发验证

安装依赖：

```bash
pip install -r requirements.txt
```

运行基础语法检查和核心回归测试：

```bash
python -m compileall plugin.py newapi_utils.py
python -m unittest test_newapi_utils.py
```

插件依赖 MaiBot 的 Host/Runner 运行环境，最终验证应在非生产 NewAPI 测试账户中完成：确认管理员账户余额不变、绑定网站用户余额增加，并检查 NewAPI 管理日志中的 `add_quota` 操作。

## 目录结构

```text
maibot_plugin_newapi/
├── _manifest.json
├── plugin.py
├── newapi_utils.py
└── test_newapi_utils.py
```

## 开源协议

MIT License
