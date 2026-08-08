import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace

from newapi_utils import NewApiCore


class FakePlugin:
    def __init__(self):
        self.config = SimpleNamespace(
            api=SimpleNamespace(api_base_url="https://newapi.test", api_access_token="test-token"),
            binding=SimpleNamespace(
                quota_display_ratio=500000.0,
                binding_group="vip",
                unbind_group="default",
            ),
            check_in=SimpleNamespace(
                enabled=True,
                timezone_offset_hours=8,
                min_display_quota=1.0,
                max_display_quota=1.0,
                double_chance=0.0,
                first_check_in_bonus_enabled=False,
                first_check_in_bonus_display_quota=0.0,
            ),
        )


class NewApiCoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.core = NewApiCore(FakePlugin(), self.temp_dir.name)
        self.assertTrue(await self.core.initialize())
        self.assertTrue(await self.core.insert_binding(1001, 2001))

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_adjust_uses_admin_manage_endpoint(self):
        calls = []

        async def fake_request(method, endpoint, json_data=None):
            calls.append((method, endpoint, json_data))
            if endpoint == "/api/user/manage":
                return {"success": True}
            if endpoint == "/api/user/2001":
                return {"success": True, "data": {"quota": 1500000}}
            self.fail(f"unexpected endpoint: {endpoint}")

        self.core.api_request = fake_request
        status, details = await self.core.adjust_balance_by_identifier(1001, 1.0)
        self.assertEqual(status, "SUCCESS")
        self.assertEqual(details["new_display_quota"], 3.0)
        self.assertEqual(
            calls[0],
            (
                "POST",
                "/api/user/manage",
                {"id": 2001, "action": "add_quota", "mode": "add", "value": 500000},
            ),
        )
        self.assertNotIn("/api/user/topup", [endpoint for _, endpoint, _ in calls])
        self.assertNotIn("/api/redemption/", [endpoint for _, endpoint, _ in calls])

    async def test_check_in_is_claimed_once_when_called_concurrently(self):
        calls = []

        async def fake_request(method, endpoint, json_data=None):
            calls.append((method, endpoint, json_data))
            if endpoint == "/api/user/manage":
                return {"success": True}
            if endpoint == "/api/user/2001":
                return {"success": True, "data": {"quota": 500000}}
            self.fail(f"unexpected endpoint: {endpoint}")

        self.core.api_request = fake_request
        results = await asyncio.gather(
            self.core.perform_check_in(1001), self.core.perform_check_in(1001)
        )
        statuses = sorted(status for status, _ in results)
        self.assertEqual(statuses, ["ALREADY_CHECKED_IN", "SUCCESS"])
        self.assertEqual(
            [endpoint for _, endpoint, _ in calls].count("/api/user/manage"), 1
        )

    async def test_failed_check_in_releases_only_its_claim(self):
        async def fake_request(method, endpoint, json_data=None):
            if endpoint == "/api/user/manage":
                return {"success": False}
            self.fail(f"unexpected endpoint: {endpoint}")

        self.core.api_request = fake_request
        status, _ = await self.core.perform_check_in(1001)
        self.assertEqual(status, "API_UPDATE_FAILED")
        binding = await self.core.get_user_by_qq(1001)
        self.assertIsNone(binding["last_check_in_time"])

    async def test_adjust_rejects_imprecise_display_amount(self):
        self.core.plugin.config.binding.quota_display_ratio = 3.0
        status, _ = await self.core.adjust_balance_by_identifier(1001, 0.5)
        self.assertEqual(status, "INVALID_AMOUNT")

    async def test_adjust_reports_balance_unknown_after_successful_update(self):
        async def fake_request(method, endpoint, json_data=None):
            if endpoint == "/api/user/manage":
                return {"success": True}
            if endpoint == "/api/user/2001":
                return None
            self.fail(f"unexpected endpoint: {endpoint}")

        self.core.api_request = fake_request
        status, _ = await self.core.adjust_balance_by_identifier(1001, 1.0)
        self.assertEqual(status, "SUCCESS_BALANCE_UNKNOWN")

    async def test_check_in_keeps_claim_when_balance_is_unknown(self):
        async def fake_request(method, endpoint, json_data=None):
            if endpoint == "/api/user/manage":
                return {"success": True}
            if endpoint == "/api/user/2001":
                return None
            self.fail(f"unexpected endpoint: {endpoint}")

        self.core.api_request = fake_request
        status, _ = await self.core.perform_check_in(1001)
        self.assertEqual(status, "SUCCESS_BALANCE_UNKNOWN")
        binding = await self.core.get_user_by_qq(1001)
        self.assertIsNotNone(binding["last_check_in_time"])

    async def test_legacy_database_gains_check_in_column(self):
        legacy_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        legacy_db = os.path.join(legacy_dir.name, "newapi_data.db")
        import sqlite3
        with sqlite3.connect(legacy_db) as conn:
            conn.execute(
                "CREATE TABLE newapi_bindings (id INTEGER PRIMARY KEY, qq_id INTEGER UNIQUE, website_user_id INTEGER NOT NULL)"
            )
        legacy_core = NewApiCore(FakePlugin(), legacy_dir.name)
        self.assertTrue(await legacy_core.initialize())
        await legacy_core.execute_query(
            "INSERT INTO newapi_bindings (qq_id, website_user_id) VALUES (%s, %s)", (3001, 4001)
        )
        self.assertIsNotNone(await legacy_core.get_user_by_qq(3001))
        legacy_dir.cleanup()

    async def test_website_user_id_is_unique(self):
        self.assertFalse(await self.core.insert_binding(1002, 2001))

    async def test_unbind_keeps_binding_when_remote_update_fails(self):
        async def fake_get(_):
            return {"id": 2001, "group": "vip"}

        async def fake_update(_):
            return False

        self.core.get_api_user_data = fake_get
        self.core.update_api_user = fake_update
        success, _ = await self.core.purge_user_binding(2001)
        self.assertFalse(success)
        self.assertIsNotNone(await self.core.get_user_by_website_id(2001))

    async def test_unbind_uses_unbind_group(self):
        captured = {}

        async def fake_get(_):
            return {"id": 2001, "group": "vip"}

        async def fake_update(profile):
            captured.update(profile)
            return True

        self.core.get_api_user_data = fake_get
        self.core.update_api_user = fake_update
        self.assertTrue(await self.core.revert_user_group(2001))
        self.assertEqual(captured["group"], "default")


if __name__ == "__main__":
    unittest.main()
