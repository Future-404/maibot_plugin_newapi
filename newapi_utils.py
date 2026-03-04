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
    NewAPI 核心工具类 (SQLite 高可靠原子化模式)。
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
        plugin_env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(plugin_env_path):
            load_dotenv(plugin_env_path, override=True)
        
        self.api_base_url = os.getenv("API_BASE_URL")
        self.api_access_token = os.getenv("API_ACCESS_TOKEN")
        self.api_admin_user_id = os.getenv("API_ADMIN_USER_ID", "1")

        if not self.api_base_url or not self.api_access_token:
            logger.error("[NewAPI Utils] API 配置不完整！初始化失败。")
            return False

        # 初始化数据库表并开启高性能模式
        try:
            await asyncio.to_thread(self._ensure_tables_exist_sync)
            logger.info("✅ [NewAPI Utils] SQLite 数据库原子化配置已就绪 (WAL Mode Enabled)。")
            return True
        except Exception as e:
            logger.error(f"❌ [NewAPI Utils] 数据库初始化失败: {e}", exc_info=True)
            return False

    def _ensure_tables_exist_sync(self):
        """同步方法：开启 WAL 模式并确认表结构。"""
        with sqlite3.connect(self.db_path) as conn:
            # 开启 WAL 模式：极大地提高并发读写性能，减少锁表概率
            conn.execute("PRAGMA journal_mode=WAL;")
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
            
            # 3. 待处理任务表 (用于分布式事务补偿)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `pending_api_tasks` (
              `id` INTEGER PRIMARY KEY AUTOINCREMENT,
              `task_type` VARCHAR(20) NOT NULL,
              `payload` TEXT NOT NULL,
              `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              `status` VARCHAR(10) DEFAULT 'PENDING'
            );
            """)
            conn.commit()

    async def execute_query(self, query: str, args: Optional[Tuple] = None, fetch: Optional[str] = None) -> Any:
        """异步执行 SQLite 查询。"""
        return await asyncio.to_thread(self._execute_query_sync, query, args, fetch)

    def _execute_query_sync(self, query: str, args: Optional[Tuple], fetch: Optional[str]) -> Any:
        """同步执行 SQLite 查询的内部方法。"""
        def dict_factory(cursor, row):
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0]] = row[idx]
            return d

        with sqlite3.connect(self.db_path) as conn:
            if fetch: conn.row_factory = dict_factory
            cursor = conn.cursor()
            sqlite_query = query.replace("%s", "?")
            cursor.execute(sqlite_query, args or ())
            
            if fetch == 'one': return cursor.fetchone()
            elif fetch == 'all': return cursor.fetchall()
            
            conn.commit()
            return cursor.rowcount

    async def api_request(self, method: str, endpoint: str, json_data: Optional[Dict] = None) -> Optional[Dict]:
        if not self.api_base_url or not self.api_access_token: return None
        url = f"{self.api_base_url}{endpoint}"
        headers = { "Authorization": self.api_access_token, "New-Api-User": self.api_admin_user_id }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=headers, json=json_data, timeout=15.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"[NewAPI Utils] API 请求异常 ({endpoint}): {e}")
            return None

    # --- 高可靠性核心方法 ---

    async def perform_check_in(self, qq_id: int, binding: Optional[Dict] = None) -> Tuple[str, Dict[str, Any]]:
        """执行签到 (原子化优化版本)。"""
        check_in_conf = self.plugin.get_config('check_in_settings', {})
        if not check_in_conf.get('enabled', False): return "DISABLED", {}
        if not binding: binding = await self.get_user_by_qq(qq_id)
        if not binding: return "NOT_BOUND", {}

        offset_hours = check_in_conf.get('timezone_offset_hours', 8)
        time_delta = timedelta(hours=offset_hours)
        local_today = (datetime.utcnow() + time_delta).date()
        
        # 1. 检查签到记录 (读)
        last_check_in_time = binding.get('last_check_in_time')
        if last_check_in_time:
            if isinstance(last_check_in_time, str):
                try: last_check_in_time = datetime.fromisoformat(last_check_in_time.replace('Z', '+00:00'))
                except: pass
            if (last_check_in_time + time_delta).date() == local_today:
                return "ALREADY_CHECKED_IN", {}

        # 2. 计算奖励
        ratio = self.plugin.get_config('binding_settings.quota_display_ratio', 500000)
        is_doubled = random.random() < check_in_conf.get('double_chance', 0.1)
        base_display_quota = random.uniform(check_in_conf.get('min_display_quota', 0), check_in_conf.get('max_display_quota', 0))
        bonus_quota = int(check_in_conf.get('first_check_in_bonus_display_quota', 0) * ratio) if last_check_in_time is None else 0
        final_quota = int(base_display_quota * ratio) * (2 if is_doubled else 1) + bonus_quota

        # 3. 【核心变更】先写本地数据库锁定状态
        # 即使 API 后面挂了，数据库已经记录了用户今天签过到，防止“回滚失败导致的刷钱”
        await self.set_check_in_time(qq_id)
        logger.info(f"[NewAPI CheckIn] 用户 {qq_id} 已在本地锁定签到状态，准备请求 API。")

        # 4. 请求 API 发放奖励
        api_user_data = await self.get_api_user_data(binding['website_user_id'])
        if not api_user_data:
            # 补偿逻辑：如果连查询都失败，本地记录其实已经存了，用户无法重试。
            # 这在安全性上是 100% 的，只是用户体验可能变差。
            return "API_UNREACHABLE", {}

        api_user_data["quota"] = api_user_data.get("quota", 0) + final_quota
        if not await self.update_api_user(api_user_data):
            logger.error(f"❌ [Critical] 用户 {qq_id} 签到 API 更新失败！金额: {final_quota}。用户已无法重试。")
            return "API_UPDATE_FAILED", {"site_id": binding['website_user_id'], "quota_owed": final_quota}
            
        return "SUCCESS", {"is_first": last_check_in_time is None, "is_doubled": is_doubled, "display_added": final_quota / ratio, "display_total": api_user_data["quota"] / ratio, "user_id": qq_id, "site_id": binding['website_user_id']}

    async def _transfer_quota(self, from_user_id: int, to_user_id: int, raw_amount: int, allow_partial: bool = False) -> Tuple[bool, int]:
        """资金转移 (增强稳健性版本)。"""
        # 由于远程 API 不支持原子跨账户，我们采用“双向确认”逻辑
        from_user = await self.get_api_user_data(from_user_id)
        to_user = await self.get_api_user_data(to_user_id)
        if not from_user or not to_user: return False, 0
        
        actual_amount = min(raw_amount, from_user.get("quota", 0)) if allow_partial else raw_amount
        if actual_amount <= 0 or (not allow_partial and from_user.get("quota", 0) < raw_amount):
            return (actual_amount == 0), 0

        # 步骤 1：从发起者账户扣款
        from_user["quota"] -= actual_amount
        if not await self.update_api_user(from_user):
            return False, 0
        
        # 步骤 2：尝试向接收者账户加款
        to_user["quota"] += actual_amount
        if not await self.update_api_user(to_user):
            # 【关键优化】如果加款失败，尝试 3 次重试回滚，如果都失败，记录到 pending_api_tasks
            logger.error(f"💥 [DANGER] 转移失败！扣款成功但加款失败。From:{from_user_id} To:{to_user_id} Amt:{actual_amount}")
            
            rollback_success = False
            for i in range(3):
                from_user["quota"] += actual_amount
                if await self.update_api_user(from_user):
                    rollback_success = True
                    break
                await asyncio.sleep(1)
            
            if not rollback_success:
                # 终极保底：写入本地待处理任务，人工介入或自动补偿
                await self.execute_query(
                    "INSERT INTO pending_api_tasks (task_type, payload) VALUES (%s, %s)",
                    ("RECOVERY_REFUND", f"from:{from_user_id},to:{to_user_id},amt:{actual_amount}")
                )
                logger.error("🛑 [FATAL] 回滚也失败了！已记录至 pending_api_tasks 待人工处理。")
            
            return False, 0
            
        return True, actual_amount

    # --- 原有方法保持兼容 ---
    async def get_user_by_qq(self, qq_id: int) -> Optional[Dict]: 
        result = await self.execute_query("SELECT * FROM newapi_bindings WHERE qq_id = %s", (qq_id,), fetch='one')
        if result and result.get('binding_time') and isinstance(result['binding_time'], str):
            try: result['binding_time'] = datetime.fromisoformat(result['binding_time'].replace('Z', '+00:00'))
            except: pass
        if result and result.get('last_check_in_time') and isinstance(result['last_check_in_time'], str):
            try: result['last_check_in_time'] = datetime.fromisoformat(result['last_check_in_time'].replace('Z', '+00:00'))
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
        if not api_user_data: return False
        leave_conf = self.plugin.get_config('group_leave_settings', {})
        revert_group = leave_conf.get('revert_group_on_leave', 'default')
        if api_user_data.get('group') != revert_group:
            api_user_data['group'] = revert_group
            return await self.update_api_user(api_user_data)
        return True

    async def purge_user_binding(self, website_user_id: int) -> Tuple[bool, Optional[Dict]]:
        binding_info = await self.get_user_by_website_id(website_user_id)
        if not binding_info: return False, None
        await self.revert_user_group(website_user_id)
        return await self.delete_binding(website_user_id=website_user_id) > 0, binding_info

    async def lookup_binding(self, identifier: int) -> Tuple[str, Optional[Dict]]:
        binding = await self.get_user_by_website_id(identifier)
        if binding: return "WEBSITE_ID", binding
        binding = await self.get_user_by_qq(identifier)
        if binding: return "QQ_ID", binding
        return "NOT_FOUND", None

    async def adjust_balance_by_identifier(self, identifier: int, display_adjustment: float) -> Tuple[str, Optional[Dict]]:
        id_type, binding = await self.lookup_binding(identifier)
        if id_type == "NOT_FOUND": return "USER_NOT_FOUND", None
        api_user_data = await self.get_api_user_data(binding['website_user_id'])
        if not api_user_data: return "API_FETCH_FAILED", {"website_user_id": binding['website_user_id']}
        ratio = self.plugin.get_config('binding_settings.quota_display_ratio', 500000)
        api_user_data["quota"] = max(0, api_user_data.get("quota", 0) + int(display_adjustment * ratio))
        if not await self.update_api_user(api_user_data): return "API_UPDATE_FAILED", {"website_user_id": binding['website_user_id']}
        return "SUCCESS", {"website_user_id": binding['website_user_id'], "new_display_quota": api_user_data["quota"] / ratio}

    async def get_today_heist_counts_by_qq(self, robber_qq_id: int) -> int:
        offset = self.plugin.get_config('check_in_settings.timezone_offset_hours', 8)
        query = f"SELECT COUNT(*) as count FROM daily_heist_log WHERE robber_qq_id = %s AND DATE(heist_time, '{offset:+} hours') = DATE('now', '{offset:+} hours')"
        result = await self.execute_query(query, (robber_qq_id,), fetch='one')
        return result['count'] if result else 0

    async def get_today_defenses_count_by_id(self, victim_website_id: int) -> int:
        offset = self.plugin.get_config('check_in_settings.timezone_offset_hours', 8)
        query = f"SELECT COUNT(*) as count FROM daily_heist_log WHERE victim_website_id = %s AND DATE(heist_time, '{offset:+} hours') = DATE('now', '{offset:+} hours') AND outcome IN ('SUCCESS', 'CRITICAL')"
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
