import os
import asyncio
import traceback
import re
from typing import List, Tuple, Type, Optional, Any, Dict, TYPE_CHECKING
from src.plugin_system import (
    BasePlugin, register_plugin, BaseCommand, ComponentInfo,
    BaseAction, ActionActivationType, BaseEventHandler, EventType,
    ConfigField
)
from src.common.logger import get_logger

if TYPE_CHECKING:
    from .newapi_utils import NewApiCore
    from .heist_logic import HeistLogic

logger = get_logger("newapi_suite")

_plugin_instance: Optional["NewApiSuitePlugin"] = None

class NewApiBaseCommand(BaseCommand):
    """NewAPI 插件命令基类（仅作为逻辑封装，不直接注册给系统）"""
    
    async def get_core(self) -> 'NewApiCore':
        from .newapi_utils import NewApiCore
        global _plugin_instance
        if _plugin_instance:
            if _plugin_instance.core is None:
                await _plugin_instance._init_core()
            return _plugin_instance.core
        raise Exception("Plugin instance not initialized")

    async def get_heist(self) -> 'HeistLogic':
        from .heist_logic import HeistLogic
        global _plugin_instance
        if _plugin_instance:
            if _plugin_instance.heist_handler is None:
                await _plugin_instance._init_core()
            return _plugin_instance.heist_handler
        raise Exception("Plugin instance not initialized")

    def get_user_id(self) -> int:
        """兼容获取用户ID"""
        if hasattr(self.message, "message_info") and self.message.message_info:
            return int(self.message.message_info.user_info.user_id)
        elif hasattr(self.message, "message_base_info"):
            return int(self.message.message_base_info.get("user_id", 0))
        return 0

    def get_target_id(self, param_name: str = "identifier") -> Optional[int]:
        """兼容获取目标ID (被@的用户)"""
        segs = []
        if hasattr(self.message, "message_segment") and self.message.message_segment:
            if self.message.message_segment.type == "seglist":
                segs = self.message.message_segment.data
            else:
                segs = [self.message.message_segment]
        elif hasattr(self.message, "message_segments") and self.message.message_segments:
            segs = self.message.message_segments
            
        def find_mentions(s_list):
            for s in s_list:
                if s.type == "mention":
                    users = s.data.get("users", [])
                    if users: return users[0].get("user_id")
                elif s.type == "seglist" and isinstance(s.data, list):
                    res = find_mentions(s.data)
                    if res: return res
            return None
        
        mention_id = find_mentions(segs)
        if mention_id: return int(mention_id)
        val = self.matched_groups.get(param_name)
        if val and val.isdigit(): return int(val)
        return None

    def is_admin(self) -> bool:
        user_id = self.get_user_id()
        admin_list = _plugin_instance.config.get("permission_settings", {}).get("admin_list", [])
        return str(user_id) in [str(admin) for admin in admin_list]

    async def send_text(self, content: str, set_reply: bool = False, reply_message: Any = None, storage_message: bool = False) -> bool:
        """计算 stream_id 并使用 text_to_stream 发送，彻底切断数据库留痕"""
        try:
            from src.plugin_system.apis import send_api
            from src.chat.message_receive.chat_stream import get_chat_manager
            
            base_info = getattr(self.message, 'message_base_info', {})
            platform = base_info.get("platform") or "discord_bot_instance_1"
            
            is_group = getattr(self.message, 'is_group_message', False)
            if not is_group and "group_id" in base_info:
                is_group = True
                
            if is_group:
                target_id = str(base_info.get("group_id", ""))
            else:
                target_id = str(base_info.get("user_id", self.get_user_id()))
                
            if not target_id or target_id == "0":
                logger.error("[Stealth Error] 无法确定目标 ID，发送失败。")
                return False
                
            # 使用 MaiBot 核心方法计算 stream_id
            stream_id = get_chat_manager().get_stream_id(platform, target_id, is_group)
            
            return await send_api.text_to_stream(
                text=content,
                stream_id=stream_id,
                set_reply=set_reply,
                reply_message=reply_message,
                storage_message=False  # 隐身模式，禁止留痕
            )
            
        except Exception as e:
            logger.error(f"[Stealth Error] 调用发送 API 失败: {e}")
            return False

class PingApiCommand(NewApiBaseCommand):
    command_name = "pingapi"
    command_pattern = r"^/pingapi"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        core = await self.get_core()
        db_status = "✅ 已连接" if os.path.exists(core.db_path) else "❓ 数据库文件未就绪"
        await self.send_text(f"🎉 Pong! NewAPI 插件套件 V1.1.0 (Power Interceptor) 正在运行！\n--------------------\n数据库状态: {db_status}")
        return True, None, True

class QueryBalanceCommand(NewApiBaseCommand):
    command_name = "查询余额"
    command_pattern = r"^/查询余额"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        user_id = self.get_user_id()
        core = await self.get_core()
        binding = await core.get_user_by_qq(user_id)
        if not binding:
            await self.send_text("您尚未绑定网站ID，无法进行此操作。\n请使用 `/绑定 [您的网站ID]` 指令。")
            return True, None, True
        website_user_id = binding['website_user_id']
        api_user_data = await core.get_api_user_data(website_user_id)
        if not api_user_data:
            await self.send_text("查询失败，无法从网站获取余额信息。")
            return True, None, True
        ratio = self.get_config("binding_settings.quota_display_ratio", 500000)
        display_quota = api_user_data.get("quota", 0) / ratio
        await self.send_text(f"查询成功！\n--------------------\n您绑定的网站ID: {website_user_id}\n当前剩余额度: {display_quota:.2f}")
        return True, None, True

class BindCommand(NewApiBaseCommand):
    command_name = "绑定"
    command_pattern = r"^/绑定\s+(?P<website_user_id>\d+)"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        website_user_id = int(self.matched_groups.get("website_user_id"))
        user_id = self.get_user_id()
        global _plugin_instance
        error_message = (await _plugin_instance._check_self_binding(user_id) or
                        await _plugin_instance._check_api_user_exists(website_user_id) or
                        await _plugin_instance._check_id_uniqueness(website_user_id))
        if error_message:
            await self.send_text(error_message)
            return True, None, True
        await self.send_text("验证通过，执行绑定...")
        success, message = await _plugin_instance._perform_binding_ritual(user_id, website_user_id)
        await self.send_text(message)
        return True, None, True

class CheckInCommand(NewApiBaseCommand):
    command_name = "签到"
    command_pattern = r"^/签到"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        user_id = self.get_user_id()
        core = await self.get_core()
        binding = await core.get_user_by_qq(user_id)
        if not binding:
            await self.send_text("您尚未绑定网站ID，无法进行此操作。\n请使用 `/绑定 [您的网站ID]` 指令。")
            return True, None, True
        status, details = await core.perform_check_in(user_id, binding=binding)
        reply = ""
        match status:
            case "SUCCESS":
                template = self.get_config('check_in_settings.check_in_success_template')
                if details["is_first"]: template = self.get_config('check_in_settings.first_check_in_success_template')
                elif details["is_doubled"]: template = self.get_config('check_in_settings.check_in_doubled_template')
                reply = template.format(display_added=f"{details['display_added']:.2f}", display_total=f"{details['display_total']:.2f}", user_id=details['user_id'], site_id=details['site_id'])
            case "DISABLED": reply = "抱歉，每日签到功能当前未开启。"
            case "ALREADY_CHECKED_IN": reply = "您今天已经签过到了，请明天再来吧！"
            case _: reply = f"签到失败: {status}"
        await self.send_text(reply)
        return True, None, True

class HeistCommand(NewApiBaseCommand):
    command_name = "打劫"
    command_pattern = r"^/打劫"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        robber_user_id = self.get_user_id()
        victim_user_id = self.get_target_id()
        if not victim_user_id:
            await self.send_text("🤔 打劫谁呢？请 @ 你要打劫的目标。")
            return True, None, True
        heist_handler = await self.get_heist()
        status, details = await heist_handler.execute_heist(robber_user_id, int(victim_user_id))
        heist_conf = self.get_config('heist_settings', {})
        reply = ""
        match status:
            case "SUCCESS": reply = heist_conf.get('success_template').format(gain=details['gain'])
            case "CRITICAL": reply = heist_conf.get('critical_template').format(gain=details['gain'])
            case "FAILURE": reply = heist_conf.get('failure_template').format(penalty=details['penalty'])
            case "DISABLED": reply = "⚔️ 打劫活动尚未开启。"
            case "ROBBER_NOT_BOUND": reply = heist_conf.get('robber_not_bound_template')
            case "VICTIM_NOT_FOUND": reply = heist_conf.get('victim_not_found_template').format(victim_identifier=f" @{victim_user_id}")
            case "CANNOT_ROB_SELF": reply = heist_conf.get('cannot_rob_self_template')
            case "ATTEMPTS_EXCEEDED": reply = heist_conf.get('attempts_exceeded_template')
            case "DEFENSES_EXCEEDED": reply = heist_conf.get('defenses_exceeded_template').format(victim_id=details['victim_id'])
            case "COOLDOWN_ACTIVE": reply = heist_conf.get('cooldown_template').format(remaining_time=details['remaining_time'])
            case _: reply = f"❓ 错误: {status}"
        await self.send_text(reply)
        return True, None, True

class UnbindCommand(NewApiBaseCommand):
    command_name = "解绑"
    command_pattern = r"^/解绑(?:\s+(?P<identifier>\d+))?"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        if not self.is_admin():
            await self.send_text("⛔ 权限不足。")
            return True, None, True
        identifier = self.get_target_id()
        if not identifier:
            await self.send_text("格式错误。")
            return True, None, True
        core = await self.get_core()
        id_type, binding = await core.lookup_binding(identifier)
        if id_type == "NOT_FOUND":
            await self.send_text("❌ 未找到绑定记录。")
            return True, None, True
        success, _ = await core.purge_user_binding(binding['website_user_id'])
        await self.send_text("✅ 解绑成功。" if success else "❌ 解绑失败。")
        return True, None, True

class LookupCommand(NewApiBaseCommand):
    command_name = "查询"
    command_pattern = r"^/查询(?:\s+(?P<identifier>\d+))?"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        if not self.is_admin():
            await self.send_text("⛔ 权限不足。")
            return True, None, True
        identifier = self.get_target_id()
        if not identifier:
            await self.send_text("格式错误。")
            return True, None, True
        core = await self.get_core()
        id_type, binding = await core.lookup_binding(identifier)
        if id_type == "NOT_FOUND":
            await self.send_text("❌ 未找到。")
        else:
            await self.send_text(f"✅ 查询成功！\n网站ID: {binding['website_user_id']}\n用户ID: {binding['qq_id']}")
        return True, None, True

class AdjustBalanceCommand(NewApiBaseCommand):
    command_name = "调整余额"
    command_pattern = r"^/调整余额(?:\s+(?P<identifier>\d+))?\s+(?P<display_adjustment>[+-]?\d+(\.\d+)?)"
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        if not self.is_admin():
            await self.send_text("⛔ 权限不足。")
            return True, None, True
        identifier = self.get_target_id()
        display_adjustment = float(self.matched_groups.get("display_adjustment", "0"))
        if not identifier:
            await self.send_text("格式错误。")
            return True, None, True
        core = await self.get_core()
        status, details = await core.adjust_balance_by_identifier(identifier, display_adjustment)
        await self.send_text(f"✅ 成功！当前余额: {details['new_display_quota']:.2f}" if status == "SUCCESS" else f"❌ 失败: {status}")
        return True, None, True

class NewApiStealthDispatcher(BaseEventHandler):
    """(权力收拢) 统一分发器：拦截所有指令并执行权限校验。"""
    event_type = EventType.ON_MESSAGE_PRE_PROCESS
    handler_name = "newapi_stealth_dispatcher"
    handler_description = "唯一指令入口：执行权限校验、指令分发与 AI 回复屏蔽。"
    weight = 10000 

    async def execute(self, message: Any) -> Tuple[bool, bool, Optional[str], Optional[Any], Optional[Any]]:
        global _plugin_instance
        if not _plugin_instance: return True, True, None, None, None
        
        try:
            # 兼容性获取原始消息
            raw = getattr(message, 'raw_message', "") or ""
            text = raw.strip()
            if not text.startswith("/"): return True, True, None, None, None

            # 获取 MaiMessages 中的基础信息字典
            base_info = getattr(message, 'message_base_info', {})
            
            # 频道ID判定
            is_group = getattr(message, 'is_group_message', False)
            if not is_group and "group_id" in base_info:
                is_group = True
                
            curr_id = base_info.get("group_id") if is_group else None
            
            # 1. 场景权限校验
            perm_conf = _plugin_instance.config.get("permission_settings", {})
            if is_group and curr_id:
                curr_id_str = str(curr_id)
                allowed_groups = perm_conf.get("allowed_groups", [])
                if allowed_groups:
                    allowed_str_list = [str(gid) for gid in allowed_groups]
                    if curr_id_str not in allowed_str_list:
                        logger.info(f"[Power Dispatch] 拒绝执行: 频道 {curr_id_str} 不在白名单内。")
                        return True, True, None, None, None
            else:
                if not perm_conf.get("enable_private_chat", True):
                    logger.info("[Power Dispatch] 拒绝执行: 私聊开关已关闭。")
                    return True, True, None, None, None

            # 2. 指令解析 (改为 search 模式以应对空格和转义符)
            commands_mapping = [
                (PingApiCommand, PingApiCommand.command_pattern),
                (QueryBalanceCommand, QueryBalanceCommand.command_pattern),
                (BindCommand, BindCommand.command_pattern),
                (CheckInCommand, CheckInCommand.command_pattern),
                (HeistCommand, HeistCommand.command_pattern),
                (UnbindCommand, UnbindCommand.command_pattern),
                (LookupCommand, LookupCommand.command_pattern),
                (AdjustBalanceCommand, AdjustBalanceCommand.command_pattern),
            ]
            
            for cmd_class, pattern in commands_mapping:
                if m := re.search(pattern, text):
                    logger.info(f"[Power Dispatch] 匹配成功: {cmd_class.command_name} (频道: {curr_id if curr_id else '私聊'})")
                    # 手动分发
                    cmd_instance = cmd_class(message, _plugin_instance.config)
                    cmd_instance.set_matched_groups(m.groupdict())
                    await cmd_instance.execute()
                    # 彻底熔断，AI 失明
                    return True, False, None, None, None
                    
        except Exception as e:
            logger.error(f"[Dispatcher Error] 拦截器异常: {e}")
            logger.error(traceback.format_exc())
            
        return True, True, None, None, None

class NewApiInitEventHandler(BaseEventHandler):
    event_type = EventType.ON_START
    handler_name = "newapi_init_on_start"
    handler_description = "初始化核心"
    weight = 100
    async def execute(self, message):
        global _plugin_instance
        if _plugin_instance: await _plugin_instance._init_core()
        return True, True, None, None, None

@register_plugin
class NewApiSuitePlugin(BasePlugin):
    plugin_name = "newapi_suite"
    enable_plugin = True
    dependencies = []
    python_dependencies = ["httpx", "python-dotenv"]
    config_file_name = "config.toml"
    config_section_descriptions = {
        "plugin": "🔌 插件基本设置",
        "permission_settings": "🛡️ 权限控制设置",
        "binding_settings": "🔗 核心绑定设置",
        "check_in_settings": "📅 签到功能设置",
        "heist_settings": "⚔️ 打劫互动设置",
        "optional_pm_settings": "📩 可选通知设置"
    }
    config_schema = {
        "plugin": {"enabled": ConfigField(label="启用插件", type=bool, default=True, description="是否开启功能"), "config_version": ConfigField(label="配置版本", type=str, default="1.1.0", description="版本")},
        "permission_settings": {
            "admin_list": ConfigField(label="管理员 ID 列表", type=list, default=[], description="管理员雪花 ID 列表"),
            "allowed_groups": ConfigField(label="允许生效的频道列表", type=list, default=[], description="Discord 频道 ID 列表。留空则允许所有群聊。"),
            "enable_private_chat": ConfigField(label="允许私聊触发", type=bool, default=True, description="是否允许在私聊中使用指令")
        },
        "binding_settings": {"binding_group": ConfigField(label="默认用户组", type=str, default="default", description="自动设置的分组"), "quota_display_ratio": ConfigField(label="额度转换比例", type=int, default=500000, description="比例")},
        "check_in_settings": {
            "enabled": ConfigField(label="启用签到", type=bool, default=True, description="是否允许 /签到"),
            "timezone_offset_hours": ConfigField(label="时区偏移", type=int, default=8, description="时区"),
            "min_display_quota": ConfigField(label="最小奖励", type=float, default=1500.0, description="奖励"),
            "max_display_quota": ConfigField(label="最大奖励", type=float, default=1500.0, description="奖励"),
            "double_chance": ConfigField(label="双倍概率", type=float, default=0.1, description="概率"),
            "first_check_in_bonus_enabled": ConfigField(label="新人礼包", type=bool, default=True, description="新人"),
            "first_check_in_bonus_display_quota": ConfigField(label="新人奖励额度", type=float, default=2.0, description="额度"),
            "check_in_success_template": ConfigField(label="成功模板", type=str, default="签到成功！您获得了 {display_added} 额度，当前剩余总额度为 {display_total}。", description="文案"),
            "check_in_doubled_template": ConfigField(label="双倍模板", type=str, default="🎉 好运连连！签到成功并触发了双倍奖励！🎉\n\n您获得了 {display_added} 额度，当前剩余总额度为 {display_total}。", description="文案"),
            "first_check_in_success_template": ConfigField(label="新人模板", type=str, default="✨ 欢迎您的第一次签到！✨\n\n您获得了 {display_added} 额度 (内含一份额外新人礼包哦！)\n当前剩余总额度为 {display_total}。", description="文案"),
        },
        "heist_settings": {
            "enabled": ConfigField(label="启用打劫", type=bool, default=True, description="开启"),
            "max_attempts_per_day": ConfigField(label="每日发起上限", type=int, default=1, description="上限"),
            "max_defenses_per_day": ConfigField(label="每日被劫上限", type=int, default=3, description="上限"),
            "min_amount": ConfigField(label="最小劫掠额度", type=float, default=5.0, description="金额"),
            "max_amount": ConfigField(label="最大劫掠额度", type=float, default=40.0, description="金额"),
            "critical_chance": ConfigField(label="暴击概率", type=float, default=0.1, description="概率"),
            "failure_chance": ConfigField(label="失败概率", type=float, default=0.5, description="概率"),
            "failure_penalty": ConfigField(label="失败赔偿额度", type=float, default=100.0, description="金额"),
            "cooldown_seconds": ConfigField(label="冷却时间(秒)", type=int, default=3600, description="间隔"),
            "success_template": ConfigField(label="成功模板", type=str, default="✅ 打劫成功！你悄悄地从对方口袋里摸走了 {gain:.2f} 额度。", description="文案"),
            "critical_template": ConfigField(label="暴击模板", type=str, default="🎉 暴击！你的手法如此娴熟，居然摸走了双倍的 {gain:.2f} 额度！", description="文案"),
            "failure_template": ConfigField(label="失败模板", type=str, default="💥 失手了！你在打劫时笨手笨脚，反被对方揍了一顿，赔偿了 {penalty:.2f} 额度。", description="文案"),
            "attempts_exceeded_template": ConfigField(label="次数超限模板", type=str, default="🥵 你今天已经打劫累了，先去歇会儿吧，明天再来。", description="提示"),
            "defenses_exceeded_template": ConfigField(label="防御超限模板", type=str, default="🛡️ 对方(ID:{victim_id})今天已经被打劫太多次了，看起来已经有了防备，换个目标吧。", description="提示"),
            "victim_not_found_template": ConfigField(label="目标未找到模板", type=str, default="💨 你朝着空气挥舞拳头，但并没有找到ID为 {victim_identifier} 的目标。", description="提示"),
            "cannot_rob_self_template": ConfigField(label="不能自劫模板", type=str, default="🤦‍♂️ 你不能打劫你自己，这毫无意义！", description="提示"),
            "robber_not_bound_template": ConfigField(label="未绑定模板", type=str, default="🤔 你自己都还没绑定账号，抢来的钱往哪儿放呢？快去 /绑定 吧！", description="提示"),
            "cooldown_template": ConfigField(label="冷却提示模板", type=str, default="⏳ 你刚刚打劫完，正在被官府通缉呢！先躲一会儿吧，还剩 {remaining_time} 秒才能再次行动。", description="提示"),
        },
        "optional_pm_settings": {"enable_bind_success_pm": ConfigField(label="绑定成功私信", type=bool, default=True, description="私信"), "bind_success_pm_template": ConfigField(label="私信模板", type=str, default="绑定成功！", description="文案")}
    }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global _plugin_instance
        _plugin_instance = self
        self.core = None
        self.heist_handler = None
        self._initialized = False
    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [(NewApiInitEventHandler.get_handler_info(), NewApiInitEventHandler), (NewApiStealthDispatcher.get_handler_info(), NewApiStealthDispatcher)]
    async def _init_core(self):
        if self._initialized: return
        from .newapi_utils import NewApiCore
        from .heist_logic import HeistLogic
        self.core = NewApiCore(self)
        await self.core.initialize()
        self.heist_handler = HeistLogic(self, self.core)
        self._initialized = True
    async def _check_self_binding(self, user_id: int) -> Optional[str]:
        if self.core is None: await self._init_core()
        if binding := await self.core.get_user_by_qq(user_id): return f"您好，您的 Discord 账号已经与网站ID {binding['website_user_id']} 签订了契约，无需重复绑定。"
        return None
    async def _check_api_user_exists(self, website_user_id: int) -> Optional[str]:
        if self.core is None: await self._init_core()
        if not await self.core.get_api_user_data(website_user_id): return f"审核失败：网站中不存在ID为 {website_user_id} 的用户。"
        return None
    async def _check_id_uniqueness(self, website_user_id: int) -> Optional[str]:
        if self.core is None: await self._init_core()
        if await self.core.get_user_by_website_id(website_user_id): return f"审核失败：ID {website_user_id} 已被他人绑定。"
        return None
    async def _perform_binding_ritual(self, user_id: int, website_user_id: int) -> Tuple[bool, str]:
        if self.core is None: await self._init_core()
        try:
            await self.core.insert_binding(user_id, website_user_id)
            api_user_data = await self.core.get_api_user_data(website_user_id)
            target_group = self.get_config('binding_settings.binding_group', 'default')
            if api_user_data:
                api_user_data['group'] = target_group
                await self.core.update_api_user(api_user_data)
            return True, f"绑定成功！已为您晋升至【{target_group}】分组。"
        except Exception as e:
            logger.error(f"绑定失败: {e}")
            if self.core: await self.core.delete_binding(qq_id=user_id)
            return False, "发生未知错误。"
