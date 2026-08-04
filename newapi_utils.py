import os
import asyncio
import httpx
import sqlite3
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Any, Dict, Tuple, List

logger = logging.getLogger("newapi_suite")

class NewApiCore:
    """
    NewAPI 核心工具类 (SQLite 原子锁 + 兑换码真实加额度模式)。
    """
    def __init__(self, plugin, data_dir: Optional[str] = None):
        self.plugin = plugin
        if data_dir:
            self.db_path = os.path.join(data_dir, "newapi_data.db")
        else:
            self.db_path = os.path.join(os.path.dirname(__file__), "newapi_data.db")
        self.api_base_url = None
        self.api_access_token = None
        self.api_admin_user_id = "1"
        logger.info("[NewAPI Utils] 核心工具类已实例化，数据库路径: %s", self.db_path)

    @staticmethod
    def _load_env_file(path: str) -> Dict[str, str]:
        env: Dict[str, str] = {}
        if not os.path.exists(path):
            return env
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
        return env

    async def initialize(self) -> bool:
        self.refresh_config()
        try:
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            await asyncio.to_thread(self._ensure_tables_exist_sync)
            logger.info("✅ [NewAPI Utils] SQLite 数据库配置已就绪。")
        except Exception as e:
            logger.error("❌ [NewAPI Utils] 数据库初始化失败: %s", e, exc_info=True)
            return False
        if not self.api_base_url or not self.api_access_token:
            logger.warning("[NewAPI Utils] API 配置不完整，请在 WebUI 或 config.toml/.env 中配置")
            return False
        return True

    def _load_config_toml(self, filepath: str) -> Dict[str, str]:
        if not os.path.exists(filepath):
            return {}
        result = {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            in_api = False
            for line in content.splitlines():
                line = line.strip()
                if line == "[api]":
                    in_api = True
                    continue
                elif line.startswith("[") and line.endswith("]"):
                    in_api = False
                if in_api and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    result[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning(f"读取 config.toml 异常: {e}")
        return result

    def refresh_config(self) -> None:
        config = self.plugin.config.api
        self.api_base_url = config.api_base_url or ""
        self.api_access_token = config.api_access_token or ""
        self.api_admin_user_id = config.api_admin_user_id or "1"

        if not self.api_base_url or not self.api_access_token:
            plugin_dir = os.path.dirname(__file__)
            toml_data = self._load_config_toml(os.path.join(plugin_dir, "config.toml"))
            env_data = self._load_env_file(os.path.join(plugin_dir, ".env"))

            self.api_base_url = self.api_base_url or toml_data.get("api_base_url") or env_data.get("API_BASE_URL", "http://172.17.0.1:3000")
            self.api_access_token = self.api_access_token or toml_data.get("api_access_token") or env_data.get("API_ACCESS_TOKEN", "9PpvvEWCqdhIvZJglUi38qVcBB0BWknR")
            self.api_admin_user_id = self.api_admin_user_id or toml_data.get("api_admin_user_id") or env_data.get("API_ADMIN_USER_ID", "1")

    def _ensure_tables_exist_sync(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS newapi_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    qq_id INTEGER UNIQUE NOT NULL,
                    website_user_id INTEGER NOT NULL,
                    binding_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check_in_time TIMESTAMP
                )
            """)
            conn.commit()

    async def execute_query(self, query: str, params: Tuple = (), fetch: str = 'none') -> Any:
        def _sync_op():
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                q = query.replace('%s', '?')
                cursor.execute(q, params)
                if fetch == 'one':
                    row = cursor.fetchone()
                    return dict(row) if row else None
                elif fetch == 'all':
                    return [dict(r) for r in cursor.fetchall()]
                else:
                    conn.commit()
                    return cursor.rowcount
        return await asyncio.to_thread(_sync_op)

    async def api_request(self, method: str, endpoint: str, json_data: Optional[Dict] = None, custom_headers: Optional[Dict] = None) -> Optional[Dict]:
        if not self.api_base_url or not self.api_access_token:
            return None
        url = f"{self.api_base_url}{endpoint}"
        token = self.api_access_token
        auth_header = token if token.startswith("Bearer ") else f"Bearer {token}"
        headers = custom_headers or {
            "Authorization": auth_header,
            "New-Api-User": str(self.api_admin_user_id)
        }
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.request(method, url, headers=headers, json=json_data, timeout=15.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"[NewAPI Utils] API 请求异常 ({endpoint}): {e}")
            return None

    # --- 核心签到发放逻辑 ---

    async def perform_check_in(self, qq_id: int, binding: Optional[Dict] = None) -> Tuple[str, Dict[str, Any]]:
        """执行签到 (通过卡密生成与自动核销真实增加额度)"""
        check_in_conf = self.plugin.config.check_in
        if not check_in_conf.enabled:
            return "DISABLED", {}
        if not binding:
            binding = await self.get_user_by_qq(qq_id)
        if not binding:
            return "NOT_BOUND", {}

        offset_hours = check_in_conf.timezone_offset_hours
        time_delta = timedelta(hours=offset_hours)
        local_today = (datetime.utcnow() + time_delta).date()
        
        # 1. 检查签到记录
        raw_last_time = binding.get('last_check_in_time')
        last_check_in_time = raw_last_time
        if last_check_in_time:
            if isinstance(last_check_in_time, str):
                try:
                    last_check_in_time = datetime.fromisoformat(last_check_in_time.replace('Z', '+00:00'))
                except:
                    pass
            if (last_check_in_time + time_delta).date() == local_today:
                return "ALREADY_CHECKED_IN", {}

        # 2. 计算奖励
        ratio = self.plugin.config.binding.quota_display_ratio
        is_doubled = random.random() < check_in_conf.double_chance
        base_display_quota = random.uniform(check_in_conf.min_display_quota, check_in_conf.max_display_quota)
        is_first = last_check_in_time is None
        bonus_quota = (
            int(check_in_conf.first_check_in_bonus_display_quota * ratio)
            if is_first and check_in_conf.first_check_in_bonus_enabled
            else 0
        )
        final_raw_quota = int(base_display_quota * ratio) * (2 if is_doubled else 1) + bonus_quota

        # 3. 先写本地数据库锁定状态 (防刷)
        await self.set_check_in_time(qq_id)
        logger.info(f"[NewAPI CheckIn] 用户 {qq_id} 已在本地锁定签到状态，准备充值发放额度: {final_raw_quota}")

        # 4. 生成卡密
        website_user_id = binding['website_user_id']
        token = self.api_access_token
        auth_header = token if token.startswith("Bearer ") else f"Bearer {token}"
        admin_headers = {
            "Authorization": auth_header,
            "New-Api-User": str(self.api_admin_user_id)
        }
        redemption_payload = {
            "name": f"checkin_{website_user_id}_{int(datetime.utcnow().timestamp())}",
            "quota": final_raw_quota,
            "count": 1
        }
        redemption_resp = await self.api_request("POST", "/api/redemption/", json_data=redemption_payload, custom_headers=admin_headers)
        if not redemption_resp or not redemption_resp.get("success") or not redemption_resp.get("data"):
            logger.error(f"❌ [NewAPI CheckIn] 用户 {qq_id} 生成兑换码失败: {redemption_resp}")
            await self.restore_check_in_time(qq_id, raw_last_time)
            return "API_UNREACHABLE", {}

        code = redemption_resp.get("data")[0]

        # 5. 自动以用户身份核销卡密
        user_headers = {
            "Authorization": auth_header,
            "New-Api-User": str(website_user_id)
        }
        topup_resp = await self.api_request("POST", "/api/user/topup", json_data={"key": code}, custom_headers=user_headers)
        if not topup_resp or not topup_resp.get("success"):
            logger.error(f"❌ [NewAPI CheckIn] 用户 {qq_id} 核销卡密失败: {topup_resp}")
            await self.restore_check_in_time(qq_id, raw_last_time)
            return "API_UPDATE_FAILED", {"site_id": website_user_id, "quota_owed": final_raw_quota}

        # 6. 查询最新余额
        user_data = await self.get_api_user_data(website_user_id)
        current_total_display = (user_data.get("quota", 0) / ratio) if user_data else 0.0

        return "SUCCESS", {
            "is_first": is_first,
            "is_doubled": is_doubled,
            "display_added": final_raw_quota / ratio,
            "display_total": current_total_display,
            "user_id": qq_id,
            "site_id": website_user_id,
        }

    # --- 辅助绑定查询与方法 ---
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

    async def set_check_in_time(self, qq_id: int) -> None:
        now_str = datetime.utcnow().isoformat()
        await self.execute_query("UPDATE newapi_bindings SET last_check_in_time = %s WHERE qq_id = %s", (now_str, qq_id))

    async def restore_check_in_time(self, qq_id: int, previous_time: Optional[Any]) -> None:
        if previous_time is None:
            query = "UPDATE newapi_bindings SET last_check_in_time = NULL WHERE qq_id = %s"
            params = (qq_id,)
        else:
            query = "UPDATE newapi_bindings SET last_check_in_time = %s WHERE qq_id = %s"
            params = (str(previous_time), qq_id)
        await self.execute_query(query, params)

    async def revert_user_group(self, website_user_id: int) -> bool:
        api_user_data = await self.get_api_user_data(website_user_id)
        if not api_user_data: return False
        revert_group = self.plugin.config.binding.binding_group
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
        website_user_id = binding['website_user_id']
        ratio = self.plugin.config.binding.quota_display_ratio
        raw_amount = int(display_adjustment * ratio)
        if raw_amount <= 0:
            return "API_UPDATE_FAILED", {"website_user_id": website_user_id}
            
        token = self.api_access_token
        auth_header = token if token.startswith("Bearer ") else f"Bearer {token}"
        admin_headers = {"Authorization": auth_header, "New-Api-User": str(self.api_admin_user_id)}
        user_headers = {"Authorization": auth_header, "New-Api-User": str(website_user_id)}
        
        red_resp = await self.api_request("POST", "/api/redemption/", json_data={"name": f"admin_adjust_{website_user_id}", "quota": raw_amount, "count": 1}, custom_headers=admin_headers)
        if not red_resp or not red_resp.get("success") or not red_resp.get("data"):
            return "API_UPDATE_FAILED", {"website_user_id": website_user_id}
        code = red_resp["data"][0]
        topup_resp = await self.api_request("POST", "/api/user/topup", json_data={"key": code}, custom_headers=user_headers)
        if not topup_resp or not topup_resp.get("success"):
            return "API_UPDATE_FAILED", {"website_user_id": website_user_id}
            
        user_data = await self.get_api_user_data(website_user_id)
        new_disp = (user_data.get("quota", 0) / ratio) if user_data else 0.0
        return "SUCCESS", {"website_user_id": website_user_id, "new_display_quota": new_disp}
