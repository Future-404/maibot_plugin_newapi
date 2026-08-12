import re
import logging
from typing import Any, Dict, Optional, Tuple, List

from pydantic import Field
from maibot_sdk import MaiBotPlugin, PluginConfigBase, Command

from .newapi_utils import NewApiCore

logger = logging.getLogger("newapi_suite")


class PluginSection(PluginConfigBase):
    __ui_label__ = "插件基础设施"
    __ui_icon__ = "settings"
    __ui_order__ = 1

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default="2.3.1", description="配置规范版本")


class ApiSettings(PluginConfigBase):
    __ui_label__ = "NewAPI 连接设置"
    __ui_icon__ = "link"
    __ui_order__ = 2

    api_base_url: str = Field(default="", description="NewAPI 系统的基础 URL")
    api_access_token: str = Field(default="", description="管理员 PAT 或访问令牌")


class PermissionSettings(PluginConfigBase):
    __ui_label__ = "权限控制"
    __ui_icon__ = "shield"
    __ui_order__ = 3

    mode: str = Field(default="all", description="运行模式: all / whitelist / blacklist")
    whitelist: List[str] = Field(default_factory=list, description="白名单列表")
    blacklist: List[str] = Field(default_factory=list, description="黑名单列表")
    admin_users: List[str] = Field(default_factory=list, description="超级管理员用户名列表（使用用户名避免 ID 精度丢失）")


class BindingSettings(PluginConfigBase):
    __ui_label__ = "账号绑定规则"
    __ui_icon__ = "user-check"
    __ui_order__ = 4

    binding_group: str = Field(default="vip", description="绑定成功后赋予的组别")
    unbind_group: str = Field(default="default", description="解绑后复原的组别")
    quota_display_ratio: float = Field(default=500000.0, gt=0, description="额度展示比例")


class CheckInSettings(PluginConfigBase):
    __ui_label__ = "每日签到规则与模版"
    __ui_icon__ = "calendar"
    __ui_order__ = 5

    enabled: bool = Field(default=True, description="是否启用签到功能")
    timezone_offset_hours: int = Field(default=8, description="时区偏移")
    min_display_quota: float = Field(default=0.1, description="签到最小额度")
    max_display_quota: float = Field(default=10.0, description="签到最大额度")
    double_chance: float = Field(default=0.1, description="翻倍概率")
    first_check_in_bonus_enabled: bool = Field(default=True, description="首次签到奖励")
    first_check_in_bonus_display_quota: float = Field(default=100.0, description="首次签到额外额度")
    check_in_success_template: str = Field(
        default="签到成功！\n您获得了 {display_added:.2f} 额度！\n当前剩余总额度为 {display_total:.2f}。",
        description="常规签到成功模板",
    )
    check_in_doubled_template: str = Field(
        default="奖励翻倍！获得了 {display_added:.2f} 额度！\n当前剩余总额度为 {display_total:.2f}。",
        description="翻倍签到成功模板",
    )
    first_check_in_success_template: str = Field(
        default="欢迎新人！您获得了 {display_added:.2f} 额度。\n当前剩余总额度为 {display_total:.2f}。",
        description="首次签到成功模板",
    )


class RobberySettings(PluginConfigBase):
    __ui_label__ = "打劫规则与文案"
    __ui_icon__ = "sword"
    __ui_order__ = 6

    enabled: bool = Field(default=True, description="是否启用打劫功能")
    success_chance: float = Field(default=0.5, ge=0, le=1, description="打劫成功概率")
    double_chance: float = Field(default=0.1, ge=0, le=1, description="成功后获得双倍额度的概率")
    base_display_quota: float = Field(default=10.0, gt=0, description="普通成功时转移的额度（兼容旧配置，优先使用随机范围）")
    min_display_quota: float = Field(default=1.0, gt=0, description="普通成功时转移的最小额度")
    max_display_quota: float = Field(default=10.0, gt=0, description="普通成功时转移的最大额度")
    cooldown_seconds: int = Field(default=300, ge=0, description="成功后的冷却秒数")
    failure_penalty_ratio: float = Field(default=0.1, ge=0, le=1, description="失败时按当前余额赔付的比例")
    failure_penalty_max_display_quota: float = Field(
        default=10.0, ge=0, description="失败赔付额度上限，0 表示不设上限"
    )
    wanted_seconds: int = Field(default=600, ge=0, description="失败后的通缉秒数")
    disabled_template: str = Field(default="打劫功能暂未开启。", description="功能关闭模板")
    self_target_template: str = Field(default="不能打劫自己哦！", description="目标为自己模板")
    robber_not_bound_template: str = Field(default="您尚未绑定网站ID，无法打劫。", description="打劫者未绑定模板")
    victim_not_bound_template: str = Field(default="对方尚未绑定网站ID，无法打劫。", description="目标未绑定模板")
    invalid_quota_ratio_template: str = Field(default="打劫失败：额度展示比例配置无效。", description="比例无效模板")
    balance_unavailable_template: str = Field(default="打劫失败：暂时无法读取双方余额。", description="余额不可读模板")
    victim_balance_empty_template: str = Field(default="对方余额不足，无从下手！", description="目标余额不足模板")
    api_update_failed_template: str = Field(default="打劫结算失败，请稍后再试。", description="结算失败模板")
    rollback_failed_template: str = Field(default="打劫结算异常，资金状态未知，请联系管理员核查。", description="回滚失败模板")
    cooldown_template: str = Field(default="打劫冷却中，请 {wait_seconds} 秒后再试。", description="冷却提示模板")
    wanted_template: str = Field(default="您正在被通缉，请 {wait_seconds} 秒后再试。", description="通缉提示模板")
    failed_template: str = Field(default="打劫失败！您赔付给对方 {display_amount:.2f} 额度，并被通缉 {wanted_seconds} 秒。", description="失败模板")
    success_template: str = Field(default="打劫得手！\n获得 {display_amount:.2f} 额度！\n当前总额度为 {display_total:.2f}。", description="成功模板")
    success_doubled_template: str = Field(default="打劫双倍得手！\n获得 {display_amount:.2f} 额度！\n当前总额度为 {display_total:.2f}。", description="双倍成功模板")
    success_balance_unknown_template: str = Field(default="打劫得手！获得 {display_amount:.2f} 额度，但暂时无法读取最新余额。", description="成功但余额未知模板")
    success_doubled_balance_unknown_template: str = Field(default="打劫双倍得手！获得 {display_amount:.2f} 额度，但暂时无法读取最新余额。", description="双倍成功但余额未知模板")
    unexpected_status_template: str = Field(default="打劫处理异常: {status}", description="未知状态模板")
    user_info_unavailable_template: str = Field(default="无法获取您的用户信息。", description="用户信息缺失模板")
    invalid_target_template: str = Field(
        default="格式错误，请使用 /打劫 @用户 或 /打劫 用户ID。", description="目标格式错误模板"
    )


class OptionalPmSettings(PluginConfigBase):
    __ui_label__ = "私聊高级开关"
    __ui_icon__ = "message-square"
    __ui_order__ = 7

    enable_all_pm: bool = Field(default=True, description="是否允许所有私聊指令")


class NewApiSuiteConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    api: ApiSettings = Field(default_factory=ApiSettings)
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    binding: BindingSettings = Field(default_factory=BindingSettings)
    check_in: CheckInSettings = Field(default_factory=CheckInSettings)
    robbery: RobberySettings = Field(default_factory=RobberySettings)
    pm: OptionalPmSettings = Field(default_factory=OptionalPmSettings)


class NewApiSuitePlugin(MaiBotPlugin):
    config_model = NewApiSuiteConfig

    def __init__(self) -> None:
        super().__init__()
        self.core: Optional[NewApiCore] = None

    async def on_load(self) -> None:
        self.core = NewApiCore(self, data_dir=str(self.ctx.paths.data_dir))
        if await self.core.initialize():
            logger.info("[NewAPI Plugin] NewAPI 核心引擎初始化成功。")
        else:
            logger.warning("[NewAPI Plugin] NewAPI 核心引擎初始化失败或 API 未配置。")

    async def on_unload(self) -> None:
        logger.info("[NewAPI Plugin] 插件已卸载。")

    async def on_config_update(
        self, scope: str, config_data: Dict[str, Any], version: str
    ) -> None:
        try:
            if scope != "self":
                return
            if self.core:
                self.core.refresh_config()
            logger.info("[NewAPI Plugin] 插件配置已更新，版本: %s", version)
        except Exception as error:
            logger.error("[NewAPI Plugin] 动态更新配置失败: %s", error)

    def _extract_username(self, message: Dict[str, Any]) -> Optional[str]:
        if not isinstance(message, dict):
            return None
        candidates = [
            message.get("username"),
            message.get("nickname"),
            (message.get("user_info") or {}).get("username"),
            (message.get("user_info") or {}).get("nickname"),
            ((message.get("message_info") or {}).get("user_info") or {}).get("username"),
            ((message.get("message_info") or {}).get("user_info") or {}).get("nickname"),
            (message.get("user") or {}).get("username"),
            (message.get("user") or {}).get("global_name"),
            (message.get("user") or {}).get("display_name"),
            (message.get("sender") or {}).get("username"),
            (message.get("sender") or {}).get("display_name"),
            (message.get("author") or {}).get("username"),
            (message.get("author") or {}).get("display_name"),
        ]
        for value in candidates:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _is_admin(self, username: Optional[str]) -> bool:
        return username is not None and username in self.config.permission.admin_users

    def _permission_allowed(self, message: Dict[str, Any]) -> bool:
        permission = self.config.permission
        channel_id = str(message.get("channel_id", ""))
        if message.get("is_private_message") or message.get("type", "") == "private":
            return self.config.pm.enable_all_pm or self._is_admin(self._extract_username(message))
        if permission.mode == "whitelist":
            return channel_id in permission.whitelist
        if permission.mode == "blacklist":
            return channel_id not in permission.blacklist
        return True

    def _extract_user_id(self, message: Dict[str, Any]) -> Optional[int]:
        if not isinstance(message, dict):
            return None
        candidates = [
            message.get("user_id"),
            message.get("sender_id"),
            message.get("author_id"),
            (message.get("user_info") or {}).get("user_id"),
            ((message.get("message_info") or {}).get("user_info") or {}).get("user_id"),
            (message.get("message_base_info") or {}).get("user_id"),
            (message.get("user") or {}).get("id"),
            (message.get("user") or {}).get("user_id"),
            (message.get("sender") or {}).get("id"),
            (message.get("sender") or {}).get("user_id"),
            (message.get("author") or {}).get("id"),
            (message.get("author") or {}).get("user_id"),
        ]
        for value in candidates:
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _extract_stream_id(self, kwargs: Dict[str, Any], message: Dict[str, Any]) -> str:
        if kwargs.get("stream_id"):
            return str(kwargs["stream_id"])
        return str(message.get("stream_id") or message.get("session_id") or message.get("channel_id") or "")

    def _extract_mention(self, message: Dict[str, Any]) -> Optional[int]:
        if not isinstance(message, dict):
            return None
        segments = message.get("message_segments", [])
        if isinstance(segments, list):
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                data = segment.get("data") or {}
                if segment.get("type") in ("at", "mention"):
                    for key in ("id", "target_id", "user_id", "target_user_id", "qq"):
                        try:
                            if data.get(key) is not None:
                                return int(data[key])
                        except (TypeError, ValueError):
                            continue
        mentions = message.get("mentions", [])
        if isinstance(mentions, list):
            for mention in mentions:
                if not isinstance(mention, dict):
                    continue
                try:
                    if mention.get("id") is not None:
                        return int(mention["id"])
                except (TypeError, ValueError):
                    continue
        content = message.get("content", "") or message.get("raw_message", "")
        if not isinstance(content, str):
            return None
        match = re.search(r"<@!?(\d+)>|\[CQ:at,qq=(\d+)\]", content)
        if match:
            return int(match.group(1) or match.group(2))
        return None

    async def _check_self_binding(self, user_id: int) -> Optional[str]:
        existing = await self.core.get_user_by_qq(user_id)
        if existing:
            return f"您已经绑定了网站ID: {existing['website_user_id']}，无需重复绑定。"
        return None

    async def _check_api_user_exists(self, website_user_id: int) -> Optional[str]:
        if not await self.core.get_api_user_data(website_user_id):
            return f"找不到网站ID为 {website_user_id} 的用户，请检查ID是否正确。"
        return None

    async def _check_id_uniqueness(self, website_user_id: int) -> Optional[str]:
        if await self.core.get_user_by_website_id(website_user_id):
            return f"网站ID {website_user_id} 已被其他用户绑定。"
        return None

    async def _perform_binding_ritual(self, user_id: int, website_user_id: int, username: Optional[str] = None) -> Tuple[bool, str]:
        profile = await self.core.get_api_user_data(website_user_id)
        if not profile:
            return False, "绑定失败，无法获取账户信息。"
        previous_group = profile.get("group")
        target_group = self.config.binding.binding_group
        profile["group"] = target_group
        if not await self.core.update_api_user(profile):
            return False, "绑定失败，无法更新网站账户分组。"
        if await self.core.insert_binding(user_id, website_user_id, username):
            return True, f"绑定成功！\n网站ID: {website_user_id}\n专属分组: {target_group}"
        if not await self.core.get_user_by_website_id(website_user_id):
            profile["group"] = previous_group
            if not await self.core.update_api_user(profile):
                logger.error("绑定本地记录失败后无法恢复网站用户 %s 的原分组", website_user_id)
        return False, "绑定失败：该用户或网站ID已被绑定。"

    async def _resolve_target(self, message: Dict[str, Any], matched: Dict[str, Any]) -> Optional[int]:
        mention = self._extract_mention(message)
        if mention is not None:
            return mention
        value = matched.get("identifier")
        try:
            if value is not None and str(value).isdigit():
                return int(value)
        except (TypeError, ValueError):
            return None
        if isinstance(value, str) and value.startswith("@"):
            binding = await self.core.get_user_by_username(value[1:])
            if binding:
                return binding["qq_id"]
        return None

    def _format_checkin_reply(self, status: str, details: Dict[str, Any]) -> str:
        if status == "NOT_BOUND":
            return "您尚未绑定网站ID，无法签到。\n请使用 `/绑定 [您的网站ID]` 指令。"
        if status == "ALREADY_CHECKED_IN":
            return "您今天已经签到过了，明天再来吧！"
        if status == "DISABLED":
            return "签到功能暂未开启。"
        if status == "SUCCESS_BALANCE_UNKNOWN":
            return f"签到额度已增加 {details['display_added']:.2f}，但暂时无法读取最新余额。"
        if status == "INVALID_QUOTA_RATIO":
            return "签到失败：额度展示比例配置无效。"
        if status == "INVALID_AMOUNT":
            return "签到失败：计算出的奖励额度无效。"
        if status == "API_UPDATE_FAILED":
            return "签到失败，无法更新 NewAPI 系统额度。"
        if status == "SUCCESS":
            config = self.config.check_in
            if details.get("is_first"):
                template = config.first_check_in_success_template
            elif details.get("is_doubled"):
                template = config.check_in_doubled_template
            else:
                template = config.check_in_success_template
            try:
                return template.format(**details)
            except (KeyError, ValueError) as error:
                logger.warning("渲染签到模板失败: %s", error)
                return (
                    f"签到成功！获得了 {details['display_added']:.2f} 额度！\n"
                    f"当前剩余总额度为 {details['display_total']:.2f}。"
                )
        return f"签到处理异常: {status}"

    def _format_robbery_reply(self, status: str, details: Dict[str, Any]) -> str:
        config = self.config.robbery
        defaults = {
            "DISABLED": "打劫功能暂未开启。",
            "SELF_TARGET": "不能打劫自己哦！",
            "ROBBER_NOT_BOUND": "您尚未绑定网站ID，无法打劫。",
            "VICTIM_NOT_BOUND": "对方尚未绑定网站ID，无法打劫。",
            "INVALID_QUOTA_RATIO": "打劫失败：额度展示比例配置无效。",
            "BALANCE_UNAVAILABLE": "打劫失败：暂时无法读取双方余额。",
            "VICTIM_BALANCE_EMPTY": "对方余额不足，无从下手！",
            "API_UPDATE_FAILED": "打劫结算失败，请稍后再试。",
            "ROLLBACK_FAILED": "打劫结算异常，资金状态未知，请联系管理员核查。",
            "COOLDOWN": "打劫冷却中，请 {wait_seconds} 秒后再试。",
            "WANTED": "您正在被通缉，请 {wait_seconds} 秒后再试。",
            "FAILED": "打劫失败！您赔付给对方 {display_amount:.2f} 额度，并被通缉 {wanted_seconds} 秒。",
            "SUCCESS": "打劫得手！\n获得 {display_amount:.2f} 额度！\n当前总额度为 {display_total:.2f}。",
            "SUCCESS_DOUBLED": "打劫双倍得手！\n获得 {display_amount:.2f} 额度！\n当前总额度为 {display_total:.2f}。",
            "SUCCESS_BALANCE_UNKNOWN": "打劫得手！获得 {display_amount:.2f} 额度，但暂时无法读取最新余额。",
            "SUCCESS_DOUBLED_BALANCE_UNKNOWN": "打劫双倍得手！获得 {display_amount:.2f} 额度，但暂时无法读取最新余额。",
            "UNEXPECTED": "打劫处理异常: {status}",
        }
        field_names = {
            "SUCCESS_DOUBLED": "success_doubled_template",
            "SUCCESS_DOUBLED_BALANCE_UNKNOWN": "success_doubled_balance_unknown_template",
            "UNEXPECTED": "unexpected_status_template",
        }
        known_statuses = set(defaults) - {"UNEXPECTED"}
        status_key = status if status in known_statuses else "UNEXPECTED"
        field_names.setdefault(status_key, f"{status_key.lower()}_template")
        message_template = getattr(
            config, field_names[status_key], defaults.get(status_key, defaults["UNEXPECTED"])
        )
        if status in ("COOLDOWN", "WANTED"):
            details = {**details, "wait_seconds": max(1, int(details.get("wait_seconds", 1)))}
        elif status == "FAILED":
            details = {**details, "wanted_seconds": config.wanted_seconds}
        elif status in ("SUCCESS", "SUCCESS_BALANCE_UNKNOWN") and details.get("is_doubled"):
            field_names_key = "SUCCESS_DOUBLED" if status == "SUCCESS" else "SUCCESS_DOUBLED_BALANCE_UNKNOWN"
            message_template = getattr(config, field_names[field_names_key], defaults[field_names_key])
        details = {**details, "status": status}
        try:
            return message_template.format(**details)
        except (IndexError, KeyError, TypeError, ValueError) as error:
            logger.warning("渲染打劫模板失败: %s", error)
            fallback = defaults.get(status, defaults["UNEXPECTED"])
            return fallback.format(**{**details, "wanted_seconds": config.wanted_seconds})

    async def _send_and_return(self, text: str, stream_id: str):
        if stream_id:
            await self.ctx.send.text(text, stream_id)
        return True, text, 2

    @Command("查询余额", pattern=r"^/查询余额$")
    async def cmd_query_balance(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            return await self._send_and_return("无法获取您的用户信息。", stream_id)
        binding = await self.core.get_user_by_qq(user_id)
        if not binding:
            return await self._send_and_return("您尚未绑定网站ID，无法进行此操作。", stream_id)
        profile = await self.core.get_api_user_data(binding["website_user_id"])
        if not profile:
            return await self._send_and_return("查询失败，无法从网站获取余额信息。", stream_id)
        ratio = self.config.binding.quota_display_ratio
        text = (
            f"查询成功！\n网站ID: {binding['website_user_id']}\n"
            f"当前剩余额度: {profile.get('quota', 0) / ratio:.2f}"
        )
        return await self._send_and_return(text, stream_id)

    @Command("绑定", pattern=r"^/绑定\s+(?P<website_user_id>\d+)$")
    async def cmd_bind(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            return await self._send_and_return("无法获取您的用户信息。", stream_id)
        website_user_id = int(kwargs.get("matched_groups", {}).get("website_user_id", "0"))
        error_message = (
            await self._check_self_binding(user_id)
            or await self._check_api_user_exists(website_user_id)
            or await self._check_id_uniqueness(website_user_id)
        )
        if error_message:
            return await self._send_and_return(error_message, stream_id)
        _, text = await self._perform_binding_ritual(user_id, website_user_id, self._extract_username(message))
        return await self._send_and_return(text, stream_id)

    @Command("签到", pattern=r"^/签到$")
    async def cmd_checkin(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        user_id = self._extract_user_id(message)
        if user_id is None:
            return await self._send_and_return("无法获取您的用户信息。", stream_id)
        status, details = await self.core.perform_check_in(user_id)
        return await self._send_and_return(self._format_checkin_reply(status, details), stream_id)

    @Command("打劫", pattern=r"^/打劫\s+(?P<identifier>\S+)$")
    async def cmd_robbery(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        robber_id = self._extract_user_id(message)
        if robber_id is None:
            return await self._send_and_return(self.config.robbery.user_info_unavailable_template, stream_id)
        victim_id = await self._resolve_target(message, kwargs.get("matched_groups", {}))
        if victim_id is None:
            return await self._send_and_return(self.config.robbery.invalid_target_template, stream_id)
        status, details = await self.core.perform_robbery(robber_id, victim_id)
        return await self._send_and_return(self._format_robbery_reply(status, details), stream_id)

    @Command("解绑", pattern=r"^/解绑(?:\s+(?P<identifier>\S+))?$")
    async def cmd_unbind(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        if not self._is_admin(self._extract_username(message)):
            return await self._send_and_return("权限不足。", stream_id)
        identifier = await self._resolve_target(message, kwargs.get("matched_groups", {}))
        if identifier is None:
            return await self._send_and_return("格式错误。", stream_id)
        binding = await self.core.lookup_binding(identifier)
        if not binding:
            return await self._send_and_return("未找到绑定记录。", stream_id)
        success, _ = await self.core.purge_user_binding(binding["website_user_id"])
        return await self._send_and_return("解绑成功。" if success else "解绑失败，已保留绑定记录以便重试。", stream_id)

    @Command("查询", pattern=r"^/查询(?:\s+(?P<identifier>\S+))?$")
    async def cmd_lookup(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        if not self._is_admin(self._extract_username(message)):
            return await self._send_and_return("权限不足。", stream_id)
        identifier = await self._resolve_target(message, kwargs.get("matched_groups", {}))
        if identifier is None:
            return await self._send_and_return("格式错误。", stream_id)
        binding = await self.core.lookup_binding(identifier)
        if not binding:
            return await self._send_and_return("未找到绑定记录。", stream_id)
        return await self._send_and_return(
            f"查询成功！\n网站ID: {binding['website_user_id']}\n用户ID: {binding['qq_id']}",
            stream_id,
        )

    @Command("调整余额", pattern=r"^/调整余额\s+(?P<identifier>\S+)\s+(?P<display_adjustment>[+-]?\d+(?:\.\d+)?)$")
    async def cmd_adjust_balance(self, **kwargs: Any):
        message = kwargs.get("message", {})
        stream_id = self._extract_stream_id(kwargs, message)
        if not self._permission_allowed(message):
            return True, "", 0
        if not self._is_admin(self._extract_username(message)):
            return await self._send_and_return("权限不足。", stream_id)
        matched = kwargs.get("matched_groups", {})
        identifier = await self._resolve_target(message, matched)
        if identifier is None:
            return await self._send_and_return("格式错误。", stream_id)
        status, details = await self.core.adjust_balance_by_identifier(
            identifier, float(matched.get("display_adjustment", "0"))
        )
        if status == "SUCCESS":
            text = f"成功增加额度！当前余额: {details['new_display_quota']:.2f}"
        elif status == "SUCCESS_BALANCE_UNKNOWN":
            text = "额度已增加，但暂时无法读取最新余额。"
        elif status == "INVALID_AMOUNT":
            text = "调整失败：仅支持大于零的增加额度。"
        elif status == "INVALID_QUOTA_RATIO":
            text = "调整失败：额度展示比例配置无效。"
        else:
            text = f"调整失败: {status}"
        return await self._send_and_return(text, stream_id)


def create_plugin():
    return NewApiSuitePlugin()
