import os
import asyncio
import httpx
import sqlite3
import random
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional, Any, Dict, Tuple

logger = logging.getLogger("newapi_suite")


class NewApiCore:
    """NewAPI 核心工具类。"""

    def __init__(self, plugin, data_dir: Optional[str] = None):
        self.plugin = plugin
        if data_dir:
            self.db_path = os.path.join(data_dir, "newapi_data.db")
        else:
            self.db_path = os.path.join(os.path.dirname(__file__), "newapi_data.db")
        self.api_base_url = ""
        self.api_access_token = ""
        logger.info("[NewAPI Utils] 数据库路径: %s", self.db_path)

    @staticmethod
    def _parse_key_value_line(line: str) -> Optional[Tuple[str, str]]:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            return None
        key, _, value = line.partition("=")
        return key.strip(), value.strip().strip('"').strip("'")

    @classmethod
    def _load_env_file(cls, path: str) -> Dict[str, str]:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as file:
            return {
                key: value
                for line in file
                if (entry := cls._parse_key_value_line(line)) is not None
                for key, value in [entry]
            }

    async def initialize(self) -> bool:
        self.refresh_config()
        try:
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            await asyncio.to_thread(self._ensure_tables_exist_sync)
            logger.info("[NewAPI Utils] SQLite 数据库已就绪。")
        except Exception as error:
            logger.error("[NewAPI Utils] 数据库初始化失败: %s", error, exc_info=True)
            return False
        if not self.api_base_url or not self.api_access_token:
            logger.warning("[NewAPI Utils] API 配置不完整，请在 WebUI 或 config.toml/.env 中配置")
            return False
        return True

    def _load_config_toml(self, filepath: str) -> Dict[str, str]:
        if not os.path.exists(filepath):
            return {}
        result: Dict[str, str] = {}
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                content = file.read()
            in_api = False
            for line in content.splitlines():
                line = line.strip()
                if line == "[api]":
                    in_api = True
                    continue
                if line.startswith("[") and line.endswith("]"):
                    in_api = False
                entry = self._parse_key_value_line(line)
                if in_api and entry:
                    key, value = entry
                    result[key] = value
        except Exception as error:
            logger.warning("读取 config.toml 异常: %s", error)
        return result

    def refresh_config(self) -> None:
        config = self.plugin.config.api
        plugin_dir = os.path.dirname(__file__)
        toml_data = self._load_config_toml(os.path.join(plugin_dir, "config.toml"))
        env_data = self._load_env_file(os.path.join(plugin_dir, ".env"))
        self.api_base_url = (
            config.api_base_url
            or toml_data.get("api_base_url")
            or env_data.get("API_BASE_URL")
            or ""
        ).rstrip("/")
        self.api_access_token = (
            config.api_access_token
            or toml_data.get("api_access_token")
            or env_data.get("API_ACCESS_TOKEN")
            or ""
        )

    def _ensure_tables_exist_sync(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS newapi_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    qq_id INTEGER UNIQUE NOT NULL,
                    website_user_id INTEGER NOT NULL,
                    binding_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check_in_time TIMESTAMP
                )
                """
            )
            columns = {
                row[1] for row in cursor.execute("PRAGMA table_info(newapi_bindings)").fetchall()
            }
            if "last_check_in_time" not in columns:
                cursor.execute("ALTER TABLE newapi_bindings ADD COLUMN last_check_in_time TIMESTAMP")
            duplicates = cursor.execute(
                """
                SELECT website_user_id FROM newapi_bindings
                GROUP BY website_user_id HAVING COUNT(*) > 1
                """
            ).fetchall()
            if duplicates:
                ids = ", ".join(str(row[0]) for row in duplicates)
                raise RuntimeError(f"发现重复网站 ID 绑定，请先清理后再启动插件: {ids}")
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_newapi_bindings_website_user_id "
                "ON newapi_bindings(website_user_id)"
            )
            conn.commit()

    async def execute_query(self, query: str, params: Tuple = (), fetch: str = "none") -> Any:
        def sync_op():
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query.replace("%s", "?"), params)
                if fetch == "one":
                    row = cursor.fetchone()
                    return dict(row) if row else None
                if fetch == "all":
                    return [dict(row) for row in cursor.fetchall()]
                conn.commit()
                return cursor.rowcount

        return await asyncio.to_thread(sync_op)

    async def api_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        if not self.api_base_url or not self.api_access_token:
            return None
        token = self.api_access_token
        headers = {
            "Authorization": token if token.startswith("Bearer ") else f"Bearer {token}",
        }
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.request(
                    method,
                    f"{self.api_base_url}{endpoint}",
                    headers=headers,
                    json=json_data,
                    timeout=15.0,
                )
                response.raise_for_status()
                return response.json()
        except Exception as error:
            logger.error("[NewAPI Utils] API 请求异常 (%s): %s", endpoint, error)
            return None

    @staticmethod
    def _parse_time(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return None
        return None

    async def _claim_check_in(self, qq_id: int, offset_hours: int) -> Tuple[Optional[str], Optional[Any]]:
        token = datetime.utcnow().isoformat(timespec="microseconds")
        local_today = (datetime.utcnow() + timedelta(hours=offset_hours)).date()

        def sync_op():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE")
                row = cursor.execute(
                    "SELECT last_check_in_time FROM newapi_bindings WHERE qq_id = ?", (qq_id,)
                ).fetchone()
                if not row:
                    return None, None
                previous = row[0]
                last_time = self._parse_time(previous)
                if last_time and (last_time + timedelta(hours=offset_hours)).date() == local_today:
                    return None, previous
                cursor.execute(
                    "UPDATE newapi_bindings SET last_check_in_time = ? WHERE qq_id = ?",
                    (token, qq_id),
                )
                conn.commit()
                return token, previous

        return await asyncio.to_thread(sync_op)

    async def _restore_check_in_claim(self, qq_id: int, token: str, previous: Optional[Any]) -> None:
        if previous is None:
            query = (
                "UPDATE newapi_bindings SET last_check_in_time = NULL "
                "WHERE qq_id = %s AND last_check_in_time = %s"
            )
            params = (qq_id, token)
        else:
            query = (
                "UPDATE newapi_bindings SET last_check_in_time = %s "
                "WHERE qq_id = %s AND last_check_in_time = %s"
            )
            params = (str(previous), qq_id, token)
        await self.execute_query(query, params)

    def _quota_ratio(self) -> Optional[float]:
        ratio = self.plugin.config.binding.quota_display_ratio
        return ratio if ratio > 0 else None

    async def add_api_user_quota(self, website_user_id: int, raw_amount: int) -> bool:
        if raw_amount <= 0:
            return False
        response = await self.api_request(
            "POST",
            "/api/user/manage",
            {
                "id": website_user_id,
                "action": "add_quota",
                "mode": "add",
                "value": raw_amount,
            },
        )
        return bool(response and response.get("success"))

    async def perform_check_in(self, qq_id: int) -> Tuple[str, Dict[str, Any]]:
        check_in_conf = self.plugin.config.check_in
        if not check_in_conf.enabled:
            return "DISABLED", {}
        binding = await self.get_user_by_qq(qq_id)
        if not binding:
            return "NOT_BOUND", {}
        ratio = self._quota_ratio()
        if ratio is None:
            return "INVALID_QUOTA_RATIO", {}

        claim_token, previous_time = await self._claim_check_in(
            qq_id, check_in_conf.timezone_offset_hours
        )
        if claim_token is None:
            return "ALREADY_CHECKED_IN", {}

        is_doubled = random.random() < check_in_conf.double_chance
        base_display_quota = random.uniform(
            check_in_conf.min_display_quota, check_in_conf.max_display_quota
        )
        is_first = previous_time is None
        bonus_quota = (
            int(check_in_conf.first_check_in_bonus_display_quota * ratio)
            if is_first and check_in_conf.first_check_in_bonus_enabled
            else 0
        )
        raw_amount = int(base_display_quota * ratio) * (2 if is_doubled else 1) + bonus_quota
        if raw_amount <= 0:
            await self._restore_check_in_claim(qq_id, claim_token, previous_time)
            return "INVALID_AMOUNT", {}

        website_user_id = binding["website_user_id"]
        if not await self.add_api_user_quota(website_user_id, raw_amount):
            await self._restore_check_in_claim(qq_id, claim_token, previous_time)
            return "API_UPDATE_FAILED", {"site_id": website_user_id}

        user_data = await self.get_api_user_data(website_user_id)
        details = {
            "is_first": is_first,
            "is_doubled": is_doubled,
            "display_added": raw_amount / ratio,
            "user_id": qq_id,
            "site_id": website_user_id,
        }
        if not user_data:
            return "SUCCESS_BALANCE_UNKNOWN", details
        details["display_total"] = user_data.get("quota", 0) / ratio
        return "SUCCESS", details

    async def get_user_by_qq(self, qq_id: int) -> Optional[Dict]:
        result = await self.execute_query(
            "SELECT * FROM newapi_bindings WHERE qq_id = %s", (qq_id,), fetch="one"
        )
        if result:
            for field in ("binding_time", "last_check_in_time"):
                if result.get(field):
                    parsed = self._parse_time(result[field])
                    if parsed:
                        result[field] = parsed
        return result

    async def get_user_by_website_id(self, website_user_id: int) -> Optional[Dict]:
        return await self.execute_query(
            "SELECT * FROM newapi_bindings WHERE website_user_id = %s",
            (website_user_id,),
            fetch="one",
        )

    async def get_api_user_data(self, user_id: int) -> Optional[Dict]:
        response = await self.api_request("GET", f"/api/user/{user_id}")
        return response.get("data") if response and response.get("success") else None

    async def update_api_user(self, user_profile: Dict) -> bool:
        response = await self.api_request("PUT", "/api/user/", user_profile)
        return bool(response and response.get("success"))

    async def insert_binding(self, qq_id: int, website_user_id: int) -> bool:
        def sync_op():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT INTO newapi_bindings (qq_id, website_user_id) VALUES (?, ?)",
                        (qq_id, website_user_id),
                    )
                return True
            except sqlite3.IntegrityError:
                return False

        return await asyncio.to_thread(sync_op)

    async def delete_binding(self, website_user_id: int) -> int:
        return await self.execute_query(
            "DELETE FROM newapi_bindings WHERE website_user_id = %s", (website_user_id,)
        )

    async def revert_user_group(self, website_user_id: int) -> bool:
        user_data = await self.get_api_user_data(website_user_id)
        if not user_data:
            return False
        revert_group = self.plugin.config.binding.unbind_group
        if user_data.get("group") == revert_group:
            return True
        user_data["group"] = revert_group
        return await self.update_api_user(user_data)

    async def purge_user_binding(self, website_user_id: int) -> Tuple[bool, Optional[Dict]]:
        binding_info = await self.get_user_by_website_id(website_user_id)
        if not binding_info or not await self.revert_user_group(website_user_id):
            return False, binding_info
        return await self.delete_binding(website_user_id) > 0, binding_info

    async def lookup_binding(self, identifier: int) -> Optional[Dict]:
        return await self.get_user_by_website_id(identifier) or await self.get_user_by_qq(identifier)

    async def adjust_balance_by_identifier(
        self, identifier: int, display_adjustment: float
    ) -> Tuple[str, Optional[Dict]]:
        binding = await self.lookup_binding(identifier)
        if not binding:
            return "USER_NOT_FOUND", None
        ratio = self._quota_ratio()
        if ratio is None:
            return "INVALID_QUOTA_RATIO", None
        try:
            amount = Decimal(str(display_adjustment)) * Decimal(str(ratio))
        except (InvalidOperation, ValueError):
            return "INVALID_AMOUNT", {"website_user_id": binding["website_user_id"]}
        if amount != amount.to_integral_value():
            return "INVALID_AMOUNT", {"website_user_id": binding["website_user_id"]}
        raw_amount = int(amount)
        if raw_amount <= 0:
            return "INVALID_AMOUNT", {"website_user_id": binding["website_user_id"]}
        website_user_id = binding["website_user_id"]
        if not await self.add_api_user_quota(website_user_id, raw_amount):
            return "API_UPDATE_FAILED", {"website_user_id": website_user_id}
        user_data = await self.get_api_user_data(website_user_id)
        if not user_data:
            return "SUCCESS_BALANCE_UNKNOWN", {"website_user_id": website_user_id}
        return "SUCCESS", {
            "website_user_id": website_user_id,
            "new_display_quota": user_data.get("quota", 0) / ratio,
        }
