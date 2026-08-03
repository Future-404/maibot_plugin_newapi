import os
import re
import logging
from typing import Any, Optional

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Command, Field, MaiBotPlugin, PluginConfigBase

logger = logging.getLogger("newapi_suite")


# ============================== 配置模型 ==============================

class PluginSection(PluginConfigBase):
    __ui_label__ = "插件基本设置"
    __ui_icon__ = "settings"
    __ui_order__ = -1

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default="2.0.0", description="配置版本")


class ApiSettings(PluginConfigBase):
    __ui_label__ = "NewAPI 连接设置"
    __ui_icon__ = "link"
    __ui_order__ = 0

    api_base_url: str = Field(default="", description="NewAPI 站点地址（如 http://your-api-domain:port）")
    api_access_token: str = Field(default="", description="API 访问令牌")
    api_admin_user_id: str = Field(default="1", description="请求 API 时使用的管理员用户 ID")


class PermissionSettings(PluginConfigBase):
    __ui_label__ = "权限控制设置"
    __ui_icon__ = "shield"
    __ui_order__ = 1

    admin_list: list[int] = Field(default_factory=list, description="管理员 ID 列表")
    allowed_groups: list[str] = Field(default_factory=list, description="允许生效的频道列表，留空则允许所有群聊")
    enable_private_chat: bool = Field(default=True, description="允许私聊触发")


class BindingSettings(PluginConfigBase):
    __ui_label__ = "核心绑定设置"
    __ui_icon__ = "link"
    __ui_order__ = 2

    binding_group: str = Field(default="default", description="自动设置的分组")
    quota_display_ratio: int = Field(default=500000, description="额度转换比例（显示额度 = quota / ratio）")


class CheckInSettings(PluginConfigBase):
    __ui_label__ = "签到功能设置"
    __ui_icon__ = "calendar"
    __ui_order__ = 3

    enabled: bool = Field(default=True, description="启用 /签到")
    timezone_offset_hours: int = Field(default=8, description="时区偏移")
    min_display_quota: float = Field(default=1500.0, description="最小奖励")
    max_display_quota: float = Field(default=1500.0, description="最大奖励")
    double_chance: float = Field(default=0.1, description="双倍概率")
    first_check_in_bonus_enabled: bool = Field(default=True, description="新人礼包")
    first_check_in_bonus_display_quota: float = Field(default=2.0, description="新人奖励额度")
    check_in_success_template: str = Field(
        default="签到成功！您获得了 {display_added} 额度，当前剩余总额度为 {display_total}。",
        description="成功模板",
    )
    check_in_doubled_template: str = Field(
        default="🎉 好运连连！签到成功并触发了双倍奖励！🎉\n\n您获得了 {display_added} 额度，当前剩余总额度为 {display_total}。",
        description="双倍模板",
    )
    first_check_in_success_template: str = Field(
        default="✨ 欢迎您的第一次签到！✨\n\n您获得了 {display_added} 额度 (内含一份额外新人礼包哦！)\n当前剩余总额度为 {display_total}。",
        description="新人模板",
    )


class HeistSettings(PluginConfigBase):
    __ui_label__ = "打劫互动设置"
    __ui_icon__ = "swords"
    __ui_order__ = 4

    enabled: bool = Field(default=True, description="启用 /打劫")
    max_attempts_per_day: int = Field(default=1, description="每日发起上限")
    max_defenses_per_day: int = Field(default=3, description="每日被劫上限")
    min_amount: float = Field(default=5.0, description="最小劫掠额度")
    max_amount: float = Field(default=40.0, description="最大劫掠额度")
    critical_chance: float = Field(default=0.1, description="暴击概率")
    failure_chance: float = Field(default=0.5, description="失败概率")
    failure_penalty: float = Field(default=100.0, description="失败赔偿额度")
    cooldown_seconds: int = Field(default=3600, description="冷却时间(秒)")
    success_template: str = Field(default="✅ 打劫成功！你悄悄地从对方口袋里摸走了 {gain:.2f} 额度。", description="成功模板")
    critical_template: str = Field(default="🎉 暴击！你的手法如此娴熟，居然摸走了双倍的 {gain:.2f} 额度！", description="暴击模板")
    failure_template: str = Field(default="💥 失手了！你在打劫时笨手笨脚，反被对方揍了一顿，赔偿了 {penalty:.2f} 额度。", description="失败模板")
    attempts_exceeded_template: str = Field(default="🥵 你今天已经打劫累了，先去歇会儿吧，明天再来。", description="次数超限模板")
    defenses_exceeded_template: str = Field(default="🛡️ 对方(ID:{victim_id})今天已经被打劫太多次了，看起来已经有了防备，换个目标吧。", description="防御超限模板")
    victim_not_found_template: str = Field(default="💨 你朝着空气挥舞拳头，但并没有找到ID为 {victim_identifier} 的目标。", description="目标未找到模板")
    cannot_rob_self_template: str = Field(default="🤦‍♂️ 你不能打劫你自己，这毫无意义！", description="不能自劫模板")
    robber_not_bound_template: str = Field(default="🤔 你自己都还没绑定账号，抢来的钱往哪儿放呢？快去 /绑定 吧！", description="未绑定模板")
    cooldown_template: str = Field(default="⏳ 你刚刚打劫完，正在被官府通缉呢！先躲一会儿吧，还剩 {remaining_time} 秒才能再次行动。", description="冷却提示模板")


class OptionalPmSettings(PluginConfigBase):
    __ui_label__ = "可选通知设置"
    __ui_icon__ = "mail"
    __ui_order__ = 5

    enable_bind_success_pm: bool = Field(default=True, description="绑定成功私信")
    bind_success_pm_template: str = Field(default="绑定成功！", description="私信模板")


class NewApiSuiteConfig(PluginConfigBase):
    __ui_label__ = "NewAPI 插件套件"
    __ui_icon__ = "wallet"

    plugin: PluginSection = Field(default_factory=PluginSection)
    api: ApiSettings = Field(default_factory=ApiSettings)
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    binding: BindingSettings = Field(default_factory=BindingSettings)
    check_in: CheckInSettings = Field(default_factory=CheckInSettings)
    heist: HeistSettings = Field(default_factory=HeistSettings)
    optional_pm: OptionalPmSettings = Field(default_factory=OptionalPmSettings)


# ============================== 插件主体 ==============================

class NewApiSuitePlugin(MaiBotPlugin):
    config_model = NewApiSuiteConfig

    def __init__(self):
        super().__init__()
        self.core: Optional["NewApiCore"] = None
        self.heist_handler: Optional["HeistLogic"] = None

    # ---------- 生命周期 ----------

    async def on_load(self) -> None:
        self.ctx.logger.info("NewAPI 插件套件加载中...")
        from .newapi_utils import NewApiCore
        from .heist_logic import HeistLogic

        self.core = NewApiCore(self, data_dir=str(self.ctx.paths.data_dir))
        init_ok = await self.core.initialize()
        self.heist_handler = HeistLogic(self, self.core)
        if not init_ok:
            self.ctx.logger.warning("插件已加载，但 API 连接配置不完整，请在 WebUI 配置后使用")
        self.ctx.logger.info("NewAPI 插件套件初始化完成")

    async def on_unload(self) -> None:
        self.ctx.logger.info("NewAPI 插件套件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            self.ctx.logger.info("插件配置已更新: version=%s", version)
            if self.core is not None:
                self.core.refresh_config()

    # ---------- 消息辅助 ----------

    @staticmethod
    def _extract_user_id(message: dict) -> Optional[int]:
        """从消息对象中兼容提取用户 ID。"""
        candidates = []
        try:
            candidates.append(message.get("user_info", {}).get("user_id"))
        except AttributeError:
            pass
        try:
            candidates.append(message.get("message_info", {}).get("user_info", {}).get("user_id"))
        except AttributeError:
            pass
        try:
            candidates.append(message.get("message_base_info", {}).get("user_id"))
        except AttributeError:
            pass
        for value in candidates:
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _extract_mention(message: dict) -> Optional[int]:
        """从消息段中查找 @提及 目标用户 ID。"""
        segments = message.get("message_segments", []) if isinstance(message, dict) else []

        def walk(items):
            for segment in items:
                if not isinstance(segment, dict):
                    continue
                seg_type = segment.get("type", "")
                data = segment.get("data") or {}
                if seg_type in ("at", "mention", "seg"):
                    for key in ("user_id", "target_user_id"):
                        value = data.get(key)
                        if value is not None:
                            try:
                                return int(value)
                            except (TypeError, ValueError):
                                pass
                    users = data.get("users") or []
                    if users and users[0].get("user_id") is not None:
                        try:
                            return int(users[0]["user_id"])
                        except (TypeError, ValueError):
                            pass
                if seg_type == "seglist" and isinstance(data, list):
                    result = walk(data)
                    if result:
                        return result
            return None

        return walk(segments)

    @staticmethod
    def _is_group_message(message: dict) -> bool:
        try:
            if message.get("is_group_message"):
                return True
        except AttributeError:
            pass
        base_info = message.get("message_base_info", {}) or {}
        return bool(base_info.get("group_id"))

    def _get_group_id(self, message: dict) -> Optional[str]:
        base_info = message.get("message_base_info", {}) or {}
        group_id = base_info.get("group_id")
        if group_id is not None:
            return str(group_id)
        try:
            group_info = message.get("message_info", {}).get("group_info", {}) or {}
            group_id = group_info.get("group_id")
            if group_id is not None:
                return str(group_id)
        except AttributeError:
            pass
        return None

    def _permission_allowed(self, message: dict) -> bool:
        """频道/私聊权限校验。"""
        permission = self.config.permission
        if self._is_group_message(message):
            allowed = [str(g) for g in permission.allowed_groups]
            if allowed:
                group_id = self._get_group_id(message)
                return bool(group_id) and group_id in allowed
            return True
        return bool(permission.enable_private_chat)

    def _is_admin(self, user_id: Optional[int]) -> bool:
        if user_id is None:
            return False
        admin_list = [str(a) for a in self.config.permission.admin_list]
        return str(user_id) in admin_list

    # ---------- 绑定校验辅助 ----------

    async def _check_self_binding(self, user_id: int) -> Optional[str]:
        if binding := await self.core.get_user_by_qq(user_id):
            return f"您好，您已绑定网站ID {binding['website_user_id']}。"
        return None

    async def _check_api_user_exists(self, website_user_id: int) -> Optional[str]:
        if not await self.core.get_api_user_data(website_user_id):
            return f"网站中不存在ID为 {website_user_id} 的用户。"
        return None

    async def _check_id_uniqueness(self, website_user_id: int) -> Optional[str]:
        if await self.core.get_user_by_website_id(website_user_id):
            return f"ID {website_user_id} 已被他人绑定。"
        return None

    async def _perform_binding_ritual(self, user_id: int, website_user_id: int) -> tuple[bool, str]:
        try:
            await self.core.insert_binding(user_id, website_user_id)
            return True, f"✅ 绑定成功！网站ID {website_user_id} 现在与您的账号关联了。"
        except Exception as exc:
            return False, f"发生错误: {exc}"

    # ---------- 回复格式化 ----------

    def _format_checkin_reply(self, status: str, details: dict) -> str:
        if status == "SUCCESS":
            check_in = self.config.check_in
            if details.get("is_first"):
                template = check_in.first_check_in_success_template
            elif details.get("is_doubled"):
                template = check_in.check_in_doubled_template
            else:
                template = check_in.check_in_success_template
            return template.format(
                display_added=f"{details['display_added']:.2f}",
                display_total=f"{details['display_total']:.2f}",
                user_id=details["user_id"],
                site_id=details["site_id"],
            )
        if status == "ALREADY_CHECKED_IN":
            return "❌ 您今天已经签过到了，请明天再来吧！"
        if status == "API_UNREACHABLE":
            return "❌ 无法连接到服务器，额度已在本地锁定，请联系管理员。"
        return f"❓ 签到失败: {status}"

    def _format_heist_reply(self, status: str, details: dict, victim_name: str) -> str:
        heist = self.config.heist
        if status == "SUCCESS":
            return heist.success_template.format(gain=details["gain"])
        if status == "CRITICAL":
            return heist.critical_template.format(gain=details["gain"])
        if status == "FAILURE":
            return heist.failure_template.format(penalty=details["penalty"])
        if status == "COOLDOWN_ACTIVE":
            return heist.cooldown_template.format(remaining_time=details["remaining_time"])
        if status == "ROBBER_NOT_BOUND":
            return heist.robber_not_bound_template
        if status == "VICTIM_NOT_FOUND":
            return heist.victim_not_found_template.format(victim_identifier=victim_name)
        if status == "ATTEMPTS_EXCEEDED":
            return heist.attempts_exceeded_template
        if status == "DEFENSES_EXCEEDED":
            return heist.defenses_exceeded_template.format(victim_id=victim_name)
        return f"行动结果: {status}"

    # ---------- 命令 ----------

    @Command("pingapi", pattern=r"^/pingapi$")
    async def cmd_pingapi(self, **kwargs: Any):
        stream_id = kwargs["stream_id"]
        db_status = "✅ 已连接" if os.path.exists(self.core.db_path) else "❓ 数据库文件未就绪"
        text = f"🎉 Pong! NewAPI 插件套件 V2.0.0 正在运行！\n--------------------\n数据库状态: {db_status}"
        await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("查询余额", pattern=r"^/查询余额$")
    async def cmd_query_balance(self, **kwargs: Any):
        stream_id = kwargs["stream_id"]
        message = kwargs.get("message", {})
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            return True, "无法获取您的用户信息。", 2
        binding = await self.core.get_user_by_qq(user_id)
        if not binding:
            text = "您尚未绑定网站ID，无法进行此操作。\n请使用 `/绑定 [您的网站ID]` 指令。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        api_user_data = await self.core.get_api_user_data(binding["website_user_id"])
        if not api_user_data:
            text = "查询失败，无法从网站获取余额信息。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        ratio = self.config.binding.quota_display_ratio
        display_quota = api_user_data.get("quota", 0) / ratio
        text = f"查询成功！\n--------------------\n您绑定的网站ID: {binding['website_user_id']}\n当前剩余额度: {display_quota:.2f}"
        await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("绑定", pattern=r"^/绑定\s+(?P<website_user_id>\d+)$")
    async def cmd_bind(self, **kwargs: Any):
        stream_id = kwargs["stream_id"]
        message = kwargs.get("message", {})
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            return True, "无法获取您的用户信息。", 2
        matched = kwargs.get("matched_groups", {})
        website_user_id = int(matched.get("website_user_id", "0"))
        error_message = (
            await self._check_self_binding(user_id)
            or await self._check_api_user_exists(website_user_id)
            or await self._check_id_uniqueness(website_user_id)
        )
        if error_message:
            await self.ctx.send.text(error_message, stream_id)
            return True, error_message, 2
        await self.ctx.send.text("验证通过，执行绑定...", stream_id)
        success, message_text = await self._perform_binding_ritual(user_id, website_user_id)
        await self.ctx.send.text(message_text, stream_id)
        return True, message_text, 2

    @Command("签到", pattern=r"^/签到$")
    async def cmd_checkin(self, **kwargs: Any):
        stream_id = kwargs["stream_id"]
        message = kwargs.get("message", {})
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            return True, "无法获取您的用户信息。", 2
        status, details = await self.core.perform_check_in(user_id)
        text = self._format_checkin_reply(status, details)
        await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("打劫", pattern=r"^/打劫")
    async def cmd_heist(self, **kwargs: Any):
        stream_id = kwargs["stream_id"]
        message = kwargs.get("message", {})
        if not self._permission_allowed(message):
            return True, "", 0
        robber_user_id = self._extract_user_id(message)
        if robber_user_id is None:
            return True, "无法获取您的用户信息。", 2
        victim_user_id = self._extract_mention(message)
        if victim_user_id is None:
            text = "🤔 打劫谁呢？请 @ 你要打劫的目标。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        status, details = await self.heist_handler.execute_heist(robber_user_id, victim_user_id)
        text = self._format_heist_reply(status, details, str(victim_user_id))
        await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("解绑", pattern=r"^/解绑(?:\s+(?P<identifier>\d+))?$")
    async def cmd_unbind(self, **kwargs: Any):
        stream_id = kwargs["stream_id"]
        message = kwargs.get("message", {})
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if not self._is_admin(user_id):
            text = "⛔ 权限不足。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        matched = kwargs.get("matched_groups", {})
        identifier = self._extract_mention(message)
        if identifier is None and matched.get("identifier"):
            identifier = int(matched["identifier"])
        if identifier is None:
            text = "格式错误。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        id_type, binding = await self.core.lookup_binding(identifier)
        if id_type == "NOT_FOUND":
            text = "❌ 未找到绑定记录。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        success, _ = await self.core.purge_user_binding(binding["website_user_id"])
        text = "✅ 解绑成功。" if success else "❌ 解绑失败。"
        await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("查询", pattern=r"^/查询(?:\s+(?P<identifier>\d+))?$")
    async def cmd_lookup(self, **kwargs: Any):
        stream_id = kwargs["stream_id"]
        message = kwargs.get("message", {})
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if not self._is_admin(user_id):
            text = "⛔ 权限不足。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        matched = kwargs.get("matched_groups", {})
        identifier = self._extract_mention(message)
        if identifier is None and matched.get("identifier"):
            identifier = int(matched["identifier"])
        if identifier is None:
            text = "格式错误。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        id_type, binding = await self.core.lookup_binding(identifier)
        if id_type == "NOT_FOUND":
            text = "❌ 未找到。"
        else:
            text = f"✅ 查询成功！\n网站ID: {binding['website_user_id']}\n用户ID: {binding['qq_id']}"
        await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("调整余额", pattern=r"^/调整余额\s+(?P<identifier>\d+)\s+(?P<display_adjustment>[+-]?\d+(\.\d+)?)$")
    async def cmd_adjust_balance(self, **kwargs: Any):
        stream_id = kwargs["stream_id"]
        message = kwargs.get("message", {})
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if not self._is_admin(user_id):
            text = "⛔ 权限不足。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        matched = kwargs.get("matched_groups", {})
        identifier = self._extract_mention(message)
        if identifier is None and matched.get("identifier"):
            identifier = int(matched["identifier"])
        if identifier is None:
            text = "格式错误。"
            await self.ctx.send.text(text, stream_id)
            return True, text, 2
        display_adjustment = float(matched.get("display_adjustment", "0"))
        status, details = await self.core.adjust_balance_by_identifier(identifier, display_adjustment)
        if status == "SUCCESS":
            text = f"✅ 成功！当前余额: {details['new_display_quota']:.2f}"
        else:
            text = f"❌ 失败: {status}"
        await self.ctx.send.text(text, stream_id)
        return True, text, 2


def create_plugin():
    return NewApiSuitePlugin()
