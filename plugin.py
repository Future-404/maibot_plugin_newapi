import os
import asyncio
import traceback
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
    """NewAPI 插件命令基类"""
    
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

    def get_target_id(self, param_name: str = "identifier") -> Optional[int]:
        """智能获取目标 ID：优先从 @提及 中获取，否则从命令参数中获取。"""
        # 1. 尝试从 @提及 中提取
        seg = self.message.message_segment
        
        def find_mentions(s):
            if s.type == "mention":
                users = s.data.get("users", [])
                if users:
                    return users[0].get("user_id")
            elif s.type == "seglist" and isinstance(s.data, list):
                for sub in s.data:
                    res = find_mentions(sub)
                    if res: return res
            return None

        mention_id = find_mentions(seg)
        if mention_id:
            return int(mention_id)
        
        # 2. 从匹配到的正则表达式分组中提取
        val = self.matched_groups.get(param_name)
        if val and val.isdigit():
            return int(val)
            
        return None

class PingApiCommand(NewApiBaseCommand):
    """响应ping命令，并报告数据库状态。"""
    command_name = "pingapi"
    command_description = "响应ping命令，并报告数据库状态。"
    command_pattern = r"^/pingapi$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        core = await self.get_core()
        db_status = "✅ 已连接" if os.path.exists(core.db_path) else "❓ 数据库文件未就绪"
        reply = f"🎉 Pong! NewAPI 插件套件 V1.1.0 正在运行！\n--------------------\n数据库状态: {db_status}"
        await self.send_text(reply)
        return True, f"Executed pingapi: {db_status}", True

class QueryBalanceCommand(NewApiBaseCommand):
    """允许已绑定用户查询网站余额。"""
    command_name = "查询余额"
    command_description = "允许已绑定用户查询网站余额。"
    command_pattern = r"^/查询余额$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        user_id = self.message.message_info.user_info.user_id
        core = await self.get_core()
        
        binding = await core.get_user_by_qq(int(user_id))
        if not binding:
            await self.send_text("您尚未绑定网站ID，无法进行此操作。\n请使用 `/绑定 [您的网站ID]` 指令。")
            return True, "User not bound", True

        website_user_id = binding['website_user_id']
        api_user_data = await core.get_api_user_data(website_user_id)

        if not api_user_data:
            await self.send_text("查询失败，无法从网站获取您的余额信息。请稍后再试或联系管理员。")
            return True, "API error", True

        ratio = self.get_config("binding_settings.quota_display_ratio", 500000)
        display_quota = api_user_data.get("quota", 0) / ratio

        reply = f"查询成功！\n--------------------\n您绑定的网站ID: {website_user_id}\n当前剩余额度: {display_quota:.2f}"
        await self.send_text(reply)
        return True, f"Queried balance for {user_id}", True

class BindCommand(NewApiBaseCommand):
    """处理用户绑定请求，并执行校验。"""
    command_name = "绑定"
    command_description = "处理用户绑定请求，并执行校验。"
    command_pattern = r"^/绑定\s+(?P<website_user_id>\d+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        website_user_id = int(self.matched_groups.get("website_user_id"))
        user_id = int(self.message.message_info.user_info.user_id)
        
        global _plugin_instance
        if not _plugin_instance:
            return False, "Plugin not initialized", False

        error_message = (
            await _plugin_instance._check_self_binding(user_id) or
            await _plugin_instance._check_api_user_exists(website_user_id) or
            await _plugin_instance._check_id_uniqueness(website_user_id)
        )
        
        if error_message:
            await self.send_text(error_message)
            return True, error_message, True
        
        await self.send_text("验证通过，执行绑定...")
        
        success, message = await _plugin_instance._perform_binding_ritual(user_id, website_user_id)
        
        await self.send_text(message)
        return True, message, True

class CheckInCommand(NewApiBaseCommand):
    """处理用户每日签到请求。"""
    command_name = "签到"
    command_description = "处理用户每日签到请求。"
    command_pattern = r"^/签到$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        user_id = int(self.message.message_info.user_info.user_id)
        core = await self.get_core()
        
        binding = await core.get_user_by_qq(user_id)
        if not binding:
            await self.send_text("您尚未绑定网站ID，无法进行此操作。\n请使用 `/绑定 [您的网站ID]` 指令。")
            return True, "User not bound", True

        status, details = await core.perform_check_in(user_id, binding=binding)
        
        reply = ""
        match status:
            case "SUCCESS":
                first_bonus_enabled = self.get_config('check_in_settings.first_check_in_bonus_enabled', False)
                
                if details["is_first"] and first_bonus_enabled:
                    template = self.get_config('check_in_settings.first_check_in_success_template')
                elif details["is_doubled"]:
                    template = self.get_config('check_in_settings.check_in_doubled_template')
                else:
                    template = self.get_config('check_in_settings.check_in_success_template')
                
                reply = template.format(
                    display_added=f"{details['display_added']:.2f}", 
                    display_total=f"{details['display_total']:.2f}",
                    user_id=details['user_id'],
                    site_id=details['site_id']
                )
            case "DISABLED":
                reply = "抱歉，每日签到功能当前未开启。"
            case "ALREADY_CHECKED_IN":
                reply = "您今天已经签过到了，请明天再来吧！"
            case "API_USER_NOT_FOUND":
                reply = "签到失败：无法获取您的网站用户信息，请联系管理员。"
            case "API_UPDATE_FAILED":
                reply = "签到失败：向网站服务器更新额度时发生错误，请稍后再试。"
            case _:
                reply = "签到时发生未知错误，请联系管理员。"
        
        await self.send_text(reply)
        return True, reply, True

class NewApiInitEventHandler(BaseEventHandler):
    """在 MaiBot 启动时初始化 NewAPI 核心"""
    event_type = EventType.ON_START
    handler_name = "newapi_init_on_start"
    handler_description = "在 MaiBot 启动时初始化 NewAPI 核心"
    weight = 100

    async def execute(self, message):
        global _plugin_instance
        if _plugin_instance:
            await _plugin_instance._init_core()
        return True, True, None, None, None

class HeistCommand(NewApiBaseCommand):
    """(娱乐) 对 @ 的目标发起打劫。"""
    command_name = "打劫"
    command_description = "(娱乐) 对 @ 的目标发起打劫。"
    command_pattern = r"^/打劫(?:\s+|$)" # 匹配以 /打劫 开头，后面跟空格或结束的消息

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        robber_user_id = int(self.message.message_info.user_info.user_id)
        
        # 使用智能方法获取目标 ID
        victim_user_id = self.get_target_id()

        if not victim_user_id:
            await self.send_text("🤔 打劫谁呢？请 @ 你要打劫的目标。")
            return True, "No target mentioned", True
        
        heist_handler = await self.get_heist()
        status, details = await heist_handler.execute_heist(robber_user_id, int(victim_user_id))
        
        heist_conf = self.get_config('heist_settings', {})
        reply = ""
        
        match status:
            case "SUCCESS":
                reply = heist_conf.get('success_template').format(gain=details['gain'])
            case "CRITICAL":
                reply = heist_conf.get('critical_template').format(gain=details['gain'])
            case "FAILURE":
                reply = heist_conf.get('failure_template').format(penalty=details['penalty'])
            case "DISABLED":
                reply = "⚔️ 打劫活动尚未开启。"
            case "ROBBER_NOT_BOUND":
                reply = heist_conf.get('robber_not_bound_template')
            case "VICTIM_NOT_FOUND":
                reply = heist_conf.get('victim_not_found_template').format(victim_identifier=f" @{victim_user_id}")
            case "CANNOT_ROB_SELF":
                reply = heist_conf.get('cannot_rob_self_template')
            case "ATTEMPTS_EXCEEDED":
                reply = heist_conf.get('attempts_exceeded_template')
            case "DEFENSES_EXCEEDED":
                reply = heist_conf.get('defenses_exceeded_template').format(victim_id=details['victim_id'])
            case "COOLDOWN_ACTIVE":
                reply = heist_conf.get('cooldown_template').format(remaining_time=details['remaining_time'])
            case "API_ERROR":
                reply = "- 发生了一个API错误，请联系管理员。"
            case _:
                reply = "❓ 发生未知错误。"
        
        await self.send_text(reply)
        # 返回 True (第三个参数) 明确告知系统拦截此消息，不再交给 LLM 处理
        return True, reply, True

class UnbindCommand(NewApiBaseCommand):
    """(管理员) 强制解除指定网站ID或用户的绑定。"""
    command_name = "解绑"
    command_description = "(管理员) 强制解除指定网站ID或用户的绑定。"
    command_pattern = r"^/解绑(?:\s+(?P<identifier>\d+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        identifier = self.get_target_id()
        if not identifier:
            await self.send_text("格式错误。请使用 `/解绑 [ID/雪花ID]` 或 `/解绑 @用户`")
            return True, "Invalid format", True
            
        core = await self.get_core()
        
        # 先识别输入的是什么
        id_type, binding = await core.lookup_binding(identifier)
        if id_type == "NOT_FOUND":
            await self.send_text(f"❌ 操作无效：未找到与 {identifier} 相关的绑定记录。")
            return True, "Not found", True
            
        website_user_id = binding['website_user_id']
        success, _ = await core.purge_user_binding(website_user_id)
        
        reply = ""
        if success:
            reply = (
                f"✅ 操作成功！\n"
                f"已将网站ID: {website_user_id}\n"
                f"从用户: {binding['qq_id']} 的契约中解放。"
            )
        else:
            reply = f"❌ 操作失败：在为网站ID {website_user_id} 执行净化时发生未知错误，请检查后台日志。"
                
        await self.send_text(reply)
        return True, reply, True

class LookupCommand(NewApiBaseCommand):
    """(管理员) 智能查询，自动识别网站ID或用户雪花ID。"""
    command_name = "查询"
    command_description = "(管理员) 智能查询，自动识别网站ID或用户雪花ID。"
    command_pattern = r"^/查询(?:\s+(?P<identifier>\d+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        identifier = self.get_target_id()
        if not identifier:
            await self.send_text("格式错误。请使用 `/查询 [ID/雪花ID]` 或 `/查询 @用户`")
            return True, "Invalid format", True
            
        core = await self.get_core()
        id_type, binding = await core.lookup_binding(identifier)
        
        reply = ""
        match id_type:
            case "WEBSITE_ID":
                reply = f"✅ 查询成功！识别为【网站ID】\n--------------------\n网站ID: {binding['website_user_id']}\n已绑定至用户: {binding['qq_id']}\n绑定时间: {binding['binding_time'].strftime('%Y-%m-%d %H:%M:%S')}"
            case "QQ_ID":
                reply = f"✅ 查询成功！识别为【用户雪花ID】\n--------------------\n用户ID: {binding['qq_id']}\n已绑定至网站ID: {binding['website_user_id']}\n绑定时间: {binding['binding_time'].strftime('%Y-%m-%d %H:%M:%S')}"
            case "NOT_FOUND":
                reply = f"❌ 查询失败：未在绑定记录中找到与 {identifier} 相关的任何信息。"
        
        await self.send_text(reply)
        return True, reply, True

class AdjustBalanceCommand(NewApiBaseCommand):
    """(管理员) 智能识别ID，并调整用户显示额度。"""
    command_name = "调整余额"
    command_description = "(管理员) 智能识别ID，并调整用户显示额度。"
    command_pattern = r"^/调整余额(?:\s+(?P<identifier>\d+))?\s+(?P<display_adjustment>[+-]?\d+(\.\d+)?)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        identifier = self.get_target_id()
        display_adjustment_str = self.matched_groups.get("display_adjustment", "0")
        display_adjustment = float(display_adjustment_str)
        
        if not identifier:
            await self.send_text("格式错误。请使用 `/调整余额 [ID/雪花ID] [额度]` 或 `/调整余额 @用户 [额度]`")
            return True, "Invalid format", True
            
        core = await self.get_core()
        status, details = await core.adjust_balance_by_identifier(identifier, display_adjustment)
        
        reply = ""
        match status:
            case "SUCCESS":
                action_text = "增加" if display_adjustment >= 0 else "减少"
                reply = f"✅ 操作成功！\n--------------------\n目标用户ID: {details['website_user_id']}\n已为其{action_text}显示额度: {abs(display_adjustment):.2f}\n该用户当前总显示额度为: {details['new_display_quota']:.2f}"
            case "USER_NOT_FOUND":
                reply = f"❌ 操作失败：未在绑定记录中找到与 {identifier} 相关的用户。"
            case "API_FETCH_FAILED":
                reply = f"❌ 操作失败：无法从网站获取ID为 {details['website_user_id']} 的用户信息。"
            case "API_UPDATE_FAILED":
                reply = f"❌ 操作失败：向网站更新ID为 {details['website_user_id']} 的余额时发生错误。"

        await self.send_text(reply)
        return True, reply, True

@register_plugin
class NewApiSuitePlugin(BasePlugin):
    """
    New API 功能套件主插件类，作为功能套件的唯一入口点。
    """
    plugin_name = "newapi_suite"
    enable_plugin = True
    dependencies = []
    python_dependencies = [
        "httpx",
        "python-dotenv"
    ]
    config_file_name = "config.toml"

    config_section_descriptions = {
        "plugin": "插件基本设置",
        "binding_settings": "核心绑定功能",
        "check_in_settings": "签到功能设置",
        "heist_settings": "打劫功能设置",
        "optional_pm_settings": "可选私信设置"
    }

    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="1.1.0", description="配置文件版本"),
        },
        "binding_settings": {
            "binding_group": ConfigField(type=str, default="default", description="绑定后自动设置的用户组"),
            "quota_display_ratio": ConfigField(type=int, default=500000, description="额度显示比例"),
        },
        "check_in_settings": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用签到"),
            "timezone_offset_hours": ConfigField(type=int, default=8, description="时区偏移"),
            "min_display_quota": ConfigField(type=float, default=1500.0, description="最小签到奖励"),
            "max_display_quota": ConfigField(type=float, default=1500.0, description="最大签到奖励"),
            "double_chance": ConfigField(type=float, default=0.1, description="双倍奖励概率"),
            "first_check_in_bonus_enabled": ConfigField(type=bool, default=True, description="首次签到奖励"),
            "first_check_in_bonus_display_quota": ConfigField(type=float, default=2.0, description="首次奖励额度"),
            "check_in_success_template": ConfigField(type=str, default="签到成功！您获得了 {display_added} 额度，当前剩余总额度为 {display_total}。", description="成功模板"),
            "check_in_doubled_template": ConfigField(type=str, default="🎉 好运连连！签到成功并触发了双倍奖励！🎉\n\n您获得了 {display_added} 额度，当前剩余总额度为 {display_total}。", description="双倍模板"),
            "first_check_in_success_template": ConfigField(type=str, default="✨ 欢迎您的第一次签到！✨\n\n您获得了 {display_added} 额度 (内含一份额外新人礼包哦！)\n当前剩余总额度为 {display_total}。", description="首次模板"),
        },
        "heist_settings": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用打劫"),
            "max_attempts_per_day": ConfigField(type=int, default=1, description="每日打劫限制"),
            "max_defenses_per_day": ConfigField(type=int, default=3, description="每日被劫限制"),
            "min_amount": ConfigField(type=float, default=5.0, description="最小劫掠额度"),
            "max_amount": ConfigField(type=float, default=40.0, description="最大劫掠额度"),
            "critical_chance": ConfigField(type=float, default=0.1, description="暴击概率"),
            "failure_chance": ConfigField(type=float, default=0.5, description="失败概率"),
            "failure_penalty": ConfigField(type=float, default=100.0, description="失败罚金"),
            "cooldown_seconds": ConfigField(type=int, default=3600, description="冷却秒数"),
            "success_template": ConfigField(type=str, default="✅ 打劫成功！你悄悄地从对方口袋里摸走了 {gain:.2f} 额度。", description="成功模板"),
            "critical_template": ConfigField(type=str, default="🎉 暴击！你的手法如此娴熟，居然摸走了双倍的 {gain:.2f} 额度！", description="暴击模板"),
            "failure_template": ConfigField(type=str, default="💥 失手了！你在打劫时笨手笨脚，反被对方揍了一顿，赔偿了 {penalty:.2f} 额度。", description="失败模板"),
            "attempts_exceeded_template": ConfigField(type=str, default="🥵 你今天已经打劫累了，先去歇会儿吧，明天再来。", description="次数超限模板"),
            "defenses_exceeded_template": ConfigField(type=str, default="🛡️ 对方(ID:{victim_id})今天已经被打劫太多次了，看起来已经有了防备，换个目标吧。", description="防御超限模板"),
            "victim_not_found_template": ConfigField(type=str, default="💨 你朝着空气挥舞拳头，但并没有找到ID为 {victim_identifier} 的目标。", description="目标未找到模板"),
            "cannot_rob_self_template": ConfigField(type=str, default="🤦‍♂️ 你不能打劫你自己，这毫无意义！", description="不能自劫模板"),
            "robber_not_bound_template": ConfigField(type=str, default="🤔 你自己都还没绑定账号，抢来的钱往哪儿放呢？快去 /绑定 吧！", description="未绑定模板"),
            "cooldown_template": ConfigField(type=str, default="⏳ 你刚刚打劫完，正在被官府通缉呢！先躲一会儿吧，还剩 {remaining_time} 秒才能再次行动。", description="冷却模板"),
        },
        "optional_pm_settings": {
            "enable_bind_success_pm": ConfigField(type=bool, default=True, description="成功后发私信"),
            "bind_success_pm_template": ConfigField(type=str, default="绑定成功！", description="私信模板"),
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global _plugin_instance
        _plugin_instance = self
        self.core = None
        self.heist_handler = None
        self._initialized = False

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (PingApiCommand.get_command_info(), PingApiCommand),
            (QueryBalanceCommand.get_command_info(), QueryBalanceCommand),
            (BindCommand.get_command_info(), BindCommand),
            (CheckInCommand.get_command_info(), CheckInCommand),
            (HeistCommand.get_command_info(), HeistCommand),
            (UnbindCommand.get_command_info(), UnbindCommand),
            (LookupCommand.get_command_info(), LookupCommand),
            (AdjustBalanceCommand.get_command_info(), AdjustBalanceCommand),
            (NewApiInitEventHandler.get_handler_info(), NewApiInitEventHandler),
        ]

    async def _init_core(self):
        if self._initialized:
            return
        
        from .newapi_utils import NewApiCore
        from .heist_logic import HeistLogic
        
        self.core = NewApiCore(self) 
        await self.core.initialize()
        self.heist_handler = HeistLogic(self, self.core)
        self._initialized = True

    # Helper methods for BindCommand
    async def _check_self_binding(self, user_id: int) -> Optional[str]:
        if self.core is None: await self._init_core()
        if binding := await self.core.get_user_by_qq(user_id):
            return f"您好，您的 Discord 账号已经与网站ID {binding['website_user_id']} 签订了契约，无需重复绑定。"
        return None

    async def _check_api_user_exists(self, website_user_id: int) -> Optional[str]:
        if self.core is None: await self._init_core()
        if not await self.core.get_api_user_data(website_user_id):
            return f"审核失败：网站中不存在ID为 {website_user_id} 的用户，请检查您的ID。"
        return None

    async def _check_id_uniqueness(self, website_user_id: int) -> Optional[str]:
        if self.core is None: await self._init_core()
        if await self.core.get_user_by_website_id(website_user_id):
            return f"审核失败：ID {website_user_id} 已被另一位用户绑定，无法操作。"
        return None

    async def _perform_binding_ritual(self, user_id: int, website_user_id: int) -> Tuple[bool, str]:
        if self.core is None: await self._init_core()
        try:
            await self.core.insert_binding(user_id, website_user_id)
            
            api_user_data = await self.core.get_api_user_data(website_user_id)
            target_group = self.get_config('binding_settings.binding_group', 'default')
            
            if api_user_data:
                api_user_data['group'] = target_group
                update_success = await self.core.update_api_user(api_user_data)
                if not update_success:
                    raise Exception("API group update failed.")
            else:
                raise Exception("API user data not found during binding ritual.")

            return True, f"恭喜您！绑定成功！\n您的 Discord 账号现已与网站ID {website_user_id} 绑定。\n已自动为您晋升至【{target_group}】分组。"
        
        except Exception as e:
            logger.error(f"绑定仪式中发生错误: {e}", exc_info=True)
            await self.core.delete_binding(qq_id=user_id)
            return False, "绑定过程中发生未知错误，操作已自动撤销，请联系管理员。"
