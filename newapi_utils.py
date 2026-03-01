import os
import asyncio
import httpx
import sqlite3
import random
from datetime import datetime, timedelta
from typing import Optional, Any, Dict, Tuple, List
from dotenv import load_dotenv, find_dotenv

from src.common.logger import get_logger

logger = get_logger("newapi_suite")

class NewApiCore:
    """
    NewAPI 核心工具类 (SQLite 本地存储模式)。
    """
    def __init__(self, plugin):
        self.plugin = plugin
        self.db_path = os.path.join(os.path.dirname(__file__), "newapi_data.db")
        self.api_base_url = None
        self.api_access_token = None
        self.api_admin_user_id = "1"
        logger.info(f"[NewAPI Utils] 核心工具类已实例化，数据库路径: {self.db_path}")

    async def initialize(self) -> bool:
        """异步初始化，严格仅从插件目录加载 .env 配置。"""
        logger.info("[NewAPI Utils] 开始执行异步初始化...")
        
        # 仅尝试从插件目录加载 .env
        plugin_env_path = os.path.join(os.path.dirname(__file__), ".env")
        
        if os.path.exists(plugin_env_path):
            load_dotenv(plugin_env_path, override=True)
            logger.info(f"[NewAPI Utils] 已从插件目录加载私有配置: {plugin_env_path}")
        else:
            logger.warning(f"[NewAPI Utils] 插件私有配置文件不存在: {plugin_env_path}")

        self.api_base_url = os.getenv("API_BASE_URL")
        self.api_access_token = os.getenv("API_ACCESS_TOKEN")
        self.api_admin_user_id = os.getenv("API_ADMIN_USER_ID", "1")

        # 增加调试日志（脱敏处理）
        if self.api_base_url:
            logger.info(f"[NewAPI Utils] 成功获取 API_BASE_URL: {self.api_base_url}")
        if self.api_access_token:
            logger.info(f"[NewAPI Utils] 成功获取 API_ACCESS_TOKEN: {'*' * 8}")

        if not self.api_base_url or not self.api_access_token:
            logger.error("[NewAPI Utils] .env 文件中 API 配置不完整！初始化失败。")
            return False

        # 初始化数据库表
        try:
            await asyncio.to_thread(self._ensure_tables_exist_sync)
            logger.info("✅ [NewAPI Utils] SQLite 数据库结构已确认就绪。")
            return True
        except Exception as e:
            logger.error(f"❌ [NewAPI Utils] 数据库初始化失败: {e}", exc_info=True)
            return False

    def _ensure_tables_exist_sync(self):
        """同步方法：检查并创建数据表（在 to_thread 中运行）。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. 用户绑定信息表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `newapi_bindings` (
              `id` INTEGER PRIMARY KEY AUTOINCREMENT,
              `qq_id` BIGINT NOT NULL UNIQUE,
              `website_user_id` INTEGER NOT NULL UNIQUE,
              `binding_time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `last_check_in_time` TIMESTAMP DEFAULT NULL
            );
            """)
            
            # 2. 每日打劫日志表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `daily_heist_log` (
              `id` INTEGER PRIMARY KEY AUTOINCREMENT,
              `robber_qq_id` BIGINT NOT NULL,
              `victim_website_id` INTEGER NOT NULL,
              `heist_time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `outcome` VARCHAR(10) NOT NULL,
              `amount` INTEGER NOT NULL
            );
            """)
            conn.commit()

    async def execute_query(self, query: str, args: Optional[Tuple] = None, fetch: Optional[str] = None) -> Any:
        """异步执行 SQLite 查询。"""
        return await asyncio.to_thread(self._execute_query_sync, query, args, fetch)

    def _execute_query_sync(self, query: str, args: Optional[Tuple], fetch: Optional[str]) -> Any:
        """同步执行 SQLite 查询的内部方法。"""
        # 使用 Row 工厂使结果支持字典访问
        def dict_factory(cursor, row):
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0]] = row[idx]
            return d

        with sqlite3.connect(self.db_path) as conn:
            if fetch:
                conn.row_factory = dict_factory
            cursor = conn.cursor()
            
            # SQLite 的占位符是 ? 而不是 %s
            sqlite_query = query.replace("%s", "?")
            
            cursor.execute(sqlite_query, args or ())
            
            if fetch == 'one':
                return cursor.fetchone()
            elif fetch == 'all':
                return cursor.fetchall()
            
            conn.commit()
            return cursor.rowcount

    async def api_request(self, method: str, endpoint: str, json_data: Optional[Dict] = None) -> Optional[Dict]:
        if not self.api_base_url or not self.api_access_token:
            logger.error("[NewAPI Utils] API 配置未在初始化时成功加载，请求中止。")
            return None
        
        url = f"{self.api_base_url}{endpoint}"
        headers = { "Authorization": self.api_access_token, "New-Api-User": self.api_admin_user_id }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=headers, json=json_data, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"[NewAPI Utils] API 请求异常: {e}", exc_info=True)
            return None

    # --- 助手方法 ---
    async def get_user_by_qq(self, qq_id: int) -> Optional[Dict]: 
        result = await self.execute_query("SELECT * FROM newapi_bindings WHERE qq_id = %s", (qq_id,), fetch='one')
        if result and result.get('binding_time'):
            # 处理 SQLite 可能返回字符串时间的问题
            if isinstance(result['binding_time'], str):
                try:
                    result['binding_time'] = datetime.fromisoformat(result['binding_time'].replace('Z', '+00:00'))
                except: pass
        if result and result.get('last_check_in_time') and isinstance(result['last_check_in_time'], str):
            try:
                result['last_check_in_time'] = datetime.fromisoformat(result['last_check_in_time'].replace('Z', '+00:00'))
            except: pass
        return result

    async def get_user_by_website_id(self, website_user_id: int) -> Optional[Dict]: 
        return await self.execute_query("SELECT * FROM newapi_bindings WHERE website_user_id = %s", (website_user_id,), fetch='one')

    async def get_api_user_data(self, user_id: int) -> Optional[Dict]:
        response = await self.api_request("GET", f"/api/user/{user_id}")
        if response and response.get("success"): return response.get("data")
        return None

    async def update_api_user(self, user_profile: Dict) -> bool:
        response = await self.api_request("PUT", "/api/user/", json_data=user_profile)
        return response and response.get("success", False)

    async def insert_binding(self, qq_id: int, website_user_id: int) -> int: 
        return await self.execute_query("INSERT INTO newapi_bindings (qq_id, website_user_id) VALUES (%s, %s)", (qq_id, website_user_id))

    async def delete_binding(self, *, qq_id: Optional[int] = None, website_user_id: Optional[int] = None) -> int:
        if qq_id: return await self.execute_query("DELETE FROM newapi_bindings WHERE qq_id = %s", (qq_id,))
        if website_user_id: return await self.execute_query("DELETE FROM newapi_bindings WHERE website_user_id = %s", (website_user_id,))
        return 0

    async def set_check_in_time(self, qq_id: int) -> int:
        query = "UPDATE newapi_bindings SET last_check_in_time = %s WHERE qq_id = %s"
        return await self.execute_query(query, (datetime.utcnow().isoformat(), qq_id))

    async def revert_user_group(self, website_user_id: int) -> bool:
        api_user_data = await self.get_api_user_data(website_user_id)
        if not api_user_data:
            logger.warning(f"无法获取网站ID {website_user_id} 的用户数据，跳过用户组恢复操作。")
            return False
        leave_conf = self.plugin.get_config('group_leave_settings', {})
        revert_group = leave_conf.get('revert_group_on_leave', 'default')
        if api_user_data.get('group') != revert_group:
            api_user_data['group'] = revert_group
            update_success = await self.update_api_user(api_user_data)
            if update_success:
                logger.info(f"成功将网站用户 {website_user_id} 恢复至用户组: {revert_group}")
            else:
                logger.error(f"尝试恢复网站用户 {website_user_id} 至用户组 {revert_group} 时失败。")
            return update_success
        return True

    async def perform_check_in(self, qq_id: int, binding: Optional[Dict] = None) -> Tuple[str, Dict[str, Any]]:
        check_in_conf = self.plugin.get_config('check_in_settings', {})
        if not check_in_conf.get('enabled', False):
            return "DISABLED", {}

        if not binding:
            binding = await self.get_user_by_qq(qq_id)
        if not binding:
            return "NOT_BOUND", {}

        offset_hours = check_in_conf.get('timezone_offset_hours', 0)
        first_bonus_enabled = check_in_conf.get('first_check_in_bonus_enabled', False)
        first_bonus_display_quota = check_in_conf.get('first_check_in_bonus_display_quota', 0)
        double_chance = check_in_conf.get('double_chance', 0.0)
        min_display_q = check_in_conf.get('min_display_quota', 0)
        max_display_q = check_in_conf.get('max_display_quota', 0)
        ratio = self.plugin.get_config('binding_settings.quota_display_ratio', 500000)

        time_delta = timedelta(hours=offset_hours)
        local_today = (datetime.utcnow() + time_delta).date()
        last_check_in_time = binding.get('last_check_in_time')
        
        is_first_check_in = last_check_in_time is None

        if not is_first_check_in:
            if isinstance(last_check_in_time, str):
                try: last_check_in_time = datetime.fromisoformat(last_check_in_time.replace('Z', '+00:00'))
                except: pass
            
            local_last_check_in_date = (last_check_in_time + time_delta).date()
            if local_last_check_in_date == local_today:
                return "ALREADY_CHECKED_IN", {}

        bonus_quota = 0
        is_doubled = False
        if is_first_check_in and first_bonus_enabled:
            bonus_quota = int(first_bonus_display_quota * ratio)
        else:
            is_doubled = random.random() < double_chance
        
        base_display_quota = random.uniform(min_display_q, max_display_q)
        base_quota = int(base_display_quota * ratio)
        regular_quota = base_quota * 2 if is_doubled else base_quota
        final_quota = regular_quota + bonus_quota

        website_user_id = binding['website_user_id']
        api_user_data = await self.get_api_user_data(website_user_id)
        if not api_user_data:
            return "API_USER_NOT_FOUND", {}

        current_quota = api_user_data.get("quota", 0)
        api_user_data["quota"] = current_quota + final_quota
        
        if not await self.update_api_user(api_user_data):
            return "API_UPDATE_FAILED", {}
            
        await self.set_check_in_time(qq_id)
        
        display_added = final_quota / ratio
        display_total = (current_quota + final_quota) / ratio

        return "SUCCESS", {
            "is_first": is_first_check_in,
            "is_doubled": is_doubled,
            "display_added": display_added,
            "display_total": display_total,
            "user_id": qq_id,
            "site_id": website_user_id
        }

    async def purge_user_binding(self, website_user_id: int) -> Tuple[bool, Optional[Dict]]:
        binding_info = await self.get_user_by_website_id(website_user_id)
        if not binding_info:
            return False, None
        try:
            await self.revert_user_group(website_user_id)
            rows_affected = await self.delete_binding(website_user_id=website_user_id)
            return rows_affected > 0, binding_info
        except Exception as e:
            logger.error(f"净化失败: {e}", exc_info=True)
            return False, binding_info

    async def lookup_binding(self, identifier: int) -> Tuple[str, Optional[Dict]]:
        binding = await self.get_user_by_website_id(identifier)
        if binding: return "WEBSITE_ID", binding
        binding = await self.get_user_by_qq(identifier)
        if binding: return "QQ_ID", binding
        return "NOT_FOUND", None

    async def adjust_balance_by_identifier(self, identifier: int, display_adjustment: float) -> Tuple[str, Optional[Dict]]:
        id_type, binding = await self.lookup_binding(identifier)
        if id_type == "NOT_FOUND": return "USER_NOT_FOUND", None
        website_user_id = binding['website_user_id']
        api_user_data = await self.get_api_user_data(website_user_id)
        if not api_user_data: return "API_FETCH_FAILED", {"website_user_id": website_user_id}
        ratio = self.plugin.get_config('binding_settings.quota_display_ratio', 500000)
        raw_quota_adjustment = int(display_adjustment * ratio)
        current_raw_quota = api_user_data.get("quota", 0)
        new_total_raw_quota = max(0, current_raw_quota + raw_quota_adjustment)
        api_user_data["quota"] = new_total_raw_quota
        if not await self.update_api_user(api_user_data):
            return "API_UPDATE_FAILED", {"website_user_id": website_user_id}
        return "SUCCESS", {"website_user_id": website_user_id, "new_display_quota": new_total_raw_quota / ratio}

    async def get_today_heist_counts_by_qq(self, robber_qq_id: int) -> int:
        query = "SELECT COUNT(*) as count FROM daily_heist_log WHERE robber_qq_id = %s AND DATE(heist_time) = DATE('now', 'localtime')"
        result = await self.execute_query(query, (robber_qq_id,), fetch='one')
        return result['count'] if result else 0

    async def get_today_defenses_count_by_id(self, victim_website_id: int) -> int:
        query = "SELECT COUNT(*) as count FROM daily_heist_log WHERE victim_website_id = %s AND DATE(heist_time) = DATE('now', 'localtime') AND outcome IN ('SUCCESS', 'CRITICAL')"
        result = await self.execute_query(query, (victim_website_id,), fetch='one')
        return result['count'] if result else 0

    async def get_last_heist_time_by_qq(self, robber_qq_id: int) -> Optional[datetime]:
        query = "SELECT MAX(heist_time) as last_time FROM daily_heist_log WHERE robber_qq_id = %s"
        result = await self.execute_query(query, (robber_qq_id,), fetch='one')
        if result and result['last_time']:
            try: return datetime.fromisoformat(result['last_time'].replace('Z', '+00:00'))
            except: pass
        return None

    async def log_heist_attempt(self, robber_qq_id: int, victim_website_id: int, outcome: str, amount: int) -> int:
        query = "INSERT INTO daily_heist_log (robber_qq_id, victim_website_id, heist_time, outcome, amount) VALUES (%s, %s, %s, %s, %s)"
        return await self.execute_query(query, (robber_qq_id, victim_website_id, datetime.utcnow().isoformat(), outcome, amount))

    async def transfer_display_quota(self, from_user_id: int, to_user_id: int, display_amount: float, allow_partial: bool = False) -> Tuple[bool, float, int]:
        ratio = self.plugin.get_config('binding_settings.quota_display_ratio', 500000)
        raw_amount = int(display_amount * ratio)
        transfer_success, actual_raw_amount = await self._transfer_quota(from_user_id=from_user_id, to_user_id=to_user_id, raw_amount=raw_amount, allow_partial=allow_partial)
        return transfer_success, actual_raw_amount / ratio, actual_raw_amount

    async def _transfer_quota(self, from_user_id: int, to_user_id: int, raw_amount: int, allow_partial: bool = False) -> Tuple[bool, int]:
        from_user = await self.get_api_user_data(from_user_id)
        to_user = await self.get_api_user_data(to_user_id)
        if not from_user or not to_user: return False, 0
        from_balance = from_user.get("quota", 0)
        actual_amount = raw_amount
        if from_balance < raw_amount:
            if allow_partial: actual_amount = from_balance
            else: return False, 0
        if actual_amount <= 0: return True, 0
        from_user["quota"] -= actual_amount
        if not await self.update_api_user(from_user): return False, 0
        to_user["quota"] += actual_amount
        if not await self.update_api_user(to_user):
            from_user["quota"] += actual_amount
            await self.update_api_user(from_user)
            return False, 0
        return True, actual_amount
