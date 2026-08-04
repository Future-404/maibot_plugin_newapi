import re
import logging
from typing import Any, Dict, Optional, Tuple, List
from pydantic import Field

from maibot_sdk import MaiBotPlugin, PluginConfigBase, Command
from .newapi_utils import NewApiCore

logger = logging.getLogger("newapi_suite")


class PluginSection(PluginConfigBase):
    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default="2.0.0", description="配置规范版本")


class ApiSettings(PluginConfigBase):
    api_base_url: str = Field(default="", description="NewAPI 系统的基础 URL")
    api_access_token: str = Field(default="", description="全限 API Token (用于管理员操作)")
    api_admin_user_id: str = Field(default="1", description="拥有管理员权限的 User-ID Header")


class PermissionSettings(PluginConfigBase):
    mode: str = Field(default="all", description="运行模式: all / whitelist / blacklist")
    whitelist: List[str] = Field(default_factory=list, description="白名单列表")
    blacklist: List[str] = Field(default_factory=list, description="黑名单列表")
    admin_users: List[int] = Field(default_factory=list, description="超级管理员 ID 列表")


class BindingSettings(PluginConfigBase):
    binding_group: str = Field(default="vip", description="绑定成功后赋予的组别")
    unbind_group: str = Field(default="default", description="解绑后复原的组别")
    quota_display_ratio: float = Field(default=500000.0, description="额度展示比例")


class CheckInSettings(PluginConfigBase):
    enabled: bool = Field(default=True, description="是否启用签到功能")
    timezone_offset_hours: int = Field(default=8, description="时区偏移")
    min_display_quota: float = Field(default=0.1, description="签到最小额度")
    max_display_quota: float = Field(default=10.0, description="签到最大额度")
    double_chance: float = Field(default=0.1, description="翻倍概率")
    first_check_in_bonus_enabled: bool = Field(default=True, description="首次签到奖励")
    first_check_in_bonus_display_quota: float = Field(default=100.0, description="首次签到额外额度")


class OptionalPmSettings(PluginConfigBase):
    enable_all_pm: bool = Field(default=False, description="是否允许所有私聊指令")


class NewApiSuiteConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    api: ApiSettings = Field(default_factory=ApiSettings)
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    binding: BindingSettings = Field(default_factory=BindingSettings)
    check_in: CheckInSettings = Field(default_factory=CheckInSettings)
    pm: OptionalPmSettings = Field(default_factory=OptionalPmSettings)


class NewApiSuitePlugin(MaiBotPlugin):
    config_model = NewApiSuiteConfig

    def __init__(self) -> None:
        super().__init__()
        self._plugin_config_instance = NewApiSuiteConfig()
        self.core: Optional[NewApiCore] = None

    async def on_load(self) -> None:
        raw_config = self.ctx.config or {}
        try:
            if raw_config:
                self._plugin_config_instance = NewApiSuiteConfig(**raw_config)
        except Exception as e:
            logger.warning(f"⚠️ [NewAPI Plugin] 加载 WebUI 配置失败: {e}，将使用默认配置。")
            self._plugin_config_instance = NewApiSuiteConfig()

        data_dir = str(self.ctx.paths.data_dir)
        self.core = NewApiCore(self, data_dir=data_dir)
        init_ok = await self.core.initialize()
        if init_ok:
            logger.info("🚀 [NewAPI Plugin] NewAPI 核心引擎初始化成功！")
        else:
            logger.warning("⚠️ [NewAPI Plugin] NewAPI 核心引擎初始化存在异常或 API 未配置。")

    async def on_unload(self) -> None:
        logger.info("🛑 [NewAPI Plugin] NewAPI 插件套件已安全卸载。")

    async def on_config_update(self, new_config: Dict[str, Any]) -> None:
        try:
            self._plugin_config_instance = NewApiSuiteConfig(**new_config)
            if self.core:
                self.core.refresh_config()
            logger.info("✅ [NewAPI Plugin] 插件配置已动态更新。")
        except Exception as e:
            logger.error(f"❌ [NewAPI Plugin] 动态更新配置失败: {e}")

    def _is_admin(self, user_id: int) -> bool:
        return user_id in self.config.permission.admin_users

    def _permission_allowed(self, message: Dict[str, Any]) -> bool:
        perm = self.config.permission
        channel_id = str(message.get("channel_id", ""))
        message_type = message.get("type", "")

        if message_type == "private":
            if self.config.pm.enable_all_pm:
                return True
            user_id = self._extract_user_id(message)
            return user_id is not None and self._is_admin(user_id)

        if perm.mode == "whitelist":
            return channel_id in perm.whitelist
        elif perm.mode == "blacklist":
            return channel_id not in perm.blacklist
        return True

    def _extract_user_id(self, message: Dict[str, Any]) -> Optional[int]:
        if not isinstance(message, dict):
            return None
        user_info = message.get("user", {}) or {}
        sender = message.get("sender", {}) or {}
        author = message.get("author", {}) or {}

        uid = (
            message.get("user_id")
            or message.get("sender_id")
            or message.get("author_id")
            or user_info.get("id")
            or user_info.get("user_id")
            or sender.get("id")
            or sender.get("user_id")
            or author.get("id")
            or author.get("user_id")
        )
        try:
            return int(uid) if uid is not None else None
        except (ValueError, TypeError):
            return None

    def _extract_stream_id(self, kwargs: Dict[str, Any], message: Dict[str, Any]) -> str:
        if isinstance(kwargs, dict) and kwargs.get("stream_id"):
            return str(kwargs["stream_id"])
        if isinstance(message, dict):
            sid = message.get("stream_id") or message.get("session_id") or message.get("channel_id")
            if sid:
                return str(sid)
        return ""

    def _extract_mention(self, message: Dict[str, Any]) -> Optional[int]:
        content = message.get("content", "") or message.get("raw_message", "")
        match = re.search(r"<@!?(\d+)>|\[CQ:at,qq=(\d+)\]", content)
        if match:
            uid_str = match.group(1) or match.group(2)
            try:
                return int(uid_str)
            except (ValueError, TypeError):
                return None
        return None

    async def _check_self_binding(self, user_id: int) -> Optional[str]:
        existing = await self.core.get_user_by_qq(user_id)
        if existing:
            return f"❌ 您已经绑定了网站ID: {existing['website_user_id']}，无需重复绑定。"
        return None

    async def _check_api_user_exists(self, website_user_id: int) -> Optional[str]:
        api_data = await self.core.get_api_user_data(website_user_id)
        if not api_data:
            return f"❌ 找不到网站ID为 {website_user_id} 的用户，请检查ID是否正确。"
        return None

    async def _check_id_uniqueness(self, website_user_id: int) -> Optional[str]:
        bound = await self.core.get_user_by_website_id(website_user_id)
        if bound:
            return f"❌ 网站ID {website_user_id} 已被其他用户绑定。"
        return None

    async def _perform_binding_ritual(self, user_id: int, website_user_id: int) -> Tuple[bool, str]:
        api_user_data = await self.core.get_api_user_data(website_user_id)
        if not api_user_data:
            return False, "❌ 绑定失败，无法获取账户信息。"

        target_group = self.config.binding.binding_group
        api_user_data["group"] = target_group
        await self.core.update_api_user(api_user_data)
        await self.core.insert_binding(user_id, website_user_id)

        msg = f"🎉 绑定成功！\n网站ID: {website_user_id}\n专属分组: {target_group}"
        return True, msg

    def _format_checkin_reply(self, status: str, details: Dict[str, Any]) -> str:
        if status == "NOT_BOUND":
            return "您尚未绑定网站ID，无法签到。\n请使用 `/绑定 [您的网站ID]` 指令。"
        elif status == "ALREADY_CHECKED_IN":
            return "您今天已经签到过了，明天再来吧！"
        elif status == "DISABLED":
            return "签到功能暂未开启。"
        elif status in ("API_UNREACHABLE", "API_UPDATE_FAILED"):
            return "❌ 签到失败，无法连接或更新 NewAPI 系统额度。"
        elif status == "SUCCESS":
            msg = "✨ 签到成功！✨\n"
            added = details['display_added']
            if details['is_first']:
                msg += f"您获得了 {added:.2f} 额度 (已加入100额度新人礼包了哦！)\n"
            elif details['is_doubled']:
                msg += f"🎉 欧皇降临！奖励翻倍！获得了 {added:.2f} 额度！\n"
            else:
                msg += f"您获得了 {added:.2f} 额度！\n"
            msg += f"当前剩余总额度为 {details['display_total']:.2f}。"
            return msg
        return f"签到处理异常: {status}"

    @Command("查询余额", pattern=r"^/查询余额$")
    async def cmd_query_balance(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            text = "无法获取您的用户信息。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        binding = await self.core.get_user_by_qq(user_id)
        if not binding:
            text = "您尚未绑定网站ID，无法进行此操作。\n请使用 `/绑定 [您的网站ID]` 指令。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        api_user_data = await self.core.get_api_user_data(binding["website_user_id"])
        if not api_user_data:
            text = "查询失败，无法从网站获取余额信息。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        ratio = self.config.binding.quota_display_ratio
        display_quota = api_user_data.get("quota", 0) / ratio
        text = f"查询成功！\n--------------------\n您绑定的网站ID: {binding['website_user_id']}\n当前剩余额度: {display_quota:.2f}"
        if stream_id:
            await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("绑定", pattern=r"^/绑定\s+(?P<website_user_id>\d+)$")
    async def cmd_bind(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            text = "无法获取您的用户信息。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        matched = kwargs.get("matched_groups", {})
        website_user_id = int(matched.get("website_user_id", "0"))
        error_message = (
            await self._check_self_binding(user_id)
            or await self._check_api_user_exists(website_user_id)
            or await self._check_id_uniqueness(website_user_id)
        )
        if error_message:
            if stream_id:
                await self.ctx.send.text(error_message, stream_id)
            return True, error_message, 2
        if stream_id:
            await self.ctx.send.text("验证通过，执行绑定...", stream_id)
        success, message_text = await self._perform_binding_ritual(user_id, website_user_id)
        if stream_id:
            await self.ctx.send.text(message_text, stream_id)
        return True, message_text, 2

    @Command("签到", pattern=r"^/签到$")
    async def cmd_checkin(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            text = "无法获取您的用户信息。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        status, details = await self.core.perform_check_in(user_id)
        text = self._format_checkin_reply(status, details)
        if stream_id:
            await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("解绑", pattern=r"^/解绑(?:\s+(?P<identifier>\d+))?$")
    async def cmd_unbind(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if not self._is_admin(user_id):
            text = "⛔ 权限不足。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        matched = kwargs.get("matched_groups", {})
        identifier = self._extract_mention(message)
        if identifier is None and matched.get("identifier"):
            identifier = int(matched["identifier"])
        if identifier is None:
            text = "格式错误。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        id_type, binding = await self.core.lookup_binding(identifier)
        if id_type == "NOT_FOUND":
            text = "❌ 未找到绑定记录。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        success, _ = await self.core.purge_user_binding(binding["website_user_id"])
        text = "✅ 解绑成功。" if success else "❌ 解绑失败。"
        if stream_id:
            await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("查询", pattern=r"^/查询(?:\s+(?P<identifier>\d+))?$")
    async def cmd_lookup(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if not self._is_admin(user_id):
            text = "⛔ 权限不足。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        matched = kwargs.get("matched_groups", {})
        identifier = self._extract_mention(message)
        if identifier is None and matched.get("identifier"):
            identifier = int(matched["identifier"])
        if identifier is None:
            text = "格式错误。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        id_type, binding = await self.core.lookup_binding(identifier)
        if id_type == "NOT_FOUND":
            text = "❌ 未找到。"
        else:
            text = f"✅ 查询成功！\n网站ID: {binding['website_user_id']}\n用户ID: {binding['qq_id']}"
        if stream_id:
            await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("调整余额", pattern=r"^/调整余额\s+(?P<identifier>\d+)\s+(?P<display_adjustment>[+-]?\d+(\.\d+)?)$")
    async def cmd_adjust_balance(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if not self._is_admin(user_id):
            text = "⛔ 权限不足。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        matched = kwargs.get("matched_groups", {})
        identifier = self._extract_mention(message)
        if identifier is None and matched.get("identifier"):
            identifier = int(matched["identifier"])
        if identifier is None:
            text = "格式错误。"
            if stream_id:
                await self.ctx.send.text(text, stream_id)
            return True, text, 2
        display_adjustment = float(matched.get("display_adjustment", "0"))
        status, details = await self.core.adjust_balance_by_identifier(identifier, display_adjustment)
        if status == "SUCCESS":
            text = f"✅ 成功！当前余额: {details['new_display_quota']:.2f}"
        else:
            text = f"❌ 失败: {status}"
        if stream_id:
            await self.ctx.send.text(text, stream_id)
        return True, text, 2


def create_plugin():
    return NewApiSuitePlugin()
