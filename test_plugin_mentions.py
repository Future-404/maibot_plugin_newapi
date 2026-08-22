import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


class PluginMentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sdk = types.ModuleType("maibot_sdk")

        class MaiBotPlugin:
            pass

        class PluginConfigBase:
            pass

        def command(*_args, **kwargs):
            def decorate(function):
                function.__command_pattern__ = kwargs.get("pattern")
                return function

            return decorate

        sdk.MaiBotPlugin = MaiBotPlugin
        sdk.PluginConfigBase = PluginConfigBase
        sdk.Command = command
        package = types.ModuleType("newapi_suite")
        package.__path__ = [str(ROOT)]
        spec = importlib.util.spec_from_file_location(
            "newapi_suite.plugin", ROOT / "plugin.py"
        )
        module = importlib.util.module_from_spec(spec)
        injected = {
            "maibot_sdk": sdk,
            "newapi_suite": package,
            "newapi_suite.plugin": module,
        }
        patcher = patch.dict(sys.modules, injected, clear=False)
        patcher.start()
        cls.addClassCleanup(patcher.stop)

        spec.loader.exec_module(module)
        cls.plugin_class = module.NewApiSuitePlugin
        cls.command_patterns = {
            name: getattr(method, "__command_pattern__", None)
            for name, method in cls.plugin_class.__dict__.items()
        }

    def setUp(self):
        self.plugin = self.plugin_class.__new__(self.plugin_class)

    def test_extracts_discord_user_from_raw_mention_segment(self):
        message = {
            "raw_message": [
                {
                    "type": "mention",
                    "data": {
                        "users": [{"user_id": "123456789012345678"}],
                        "roles": [{"role_id": "99"}],
                    },
                },
                {"type": "text", "data": "你好"},
            ]
        }
        self.assertEqual(self.plugin._extract_mention(message), 123456789012345678)

    def test_ambiguous_user_mentions_are_rejected(self):
        message = {
            "raw_message": [
                {
                    "type": "mention",
                    "data": {"users": [{"user_id": "101"}, {"user_id": "202"}]},
                }
            ]
        }
        self.assertIsNone(self.plugin._extract_mention(message))

    def test_extracts_username_from_standard_host_message(self):
        message = {
            "message_info": {
                "user_info": {
                    "user_id": "123",
                    "user_nickname": "Discord Display Name",
                }
            }
        }
        self.assertEqual(self.plugin._extract_username(message), "Discord Display Name")

    def test_ignores_role_and_channel_only_mentions(self):
        message = {
            "raw_message": [
                {
                    "type": "mention",
                    "data": {
                        "roles": [{"role_id": "99"}],
                        "channels": [{"channel_id": "88"}],
                    },
                }
            ]
        }
        self.assertIsNone(self.plugin._extract_mention(message))

    def test_extracts_legacy_discord_and_cq_mentions(self):
        self.assertEqual(self.plugin._extract_mention({"content": "<@!456>"}), 456)
        self.assertEqual(
            self.plugin._extract_mention({"content": "[CQ:at,qq=789]"}), 789
        )

    def test_command_patterns_accept_spaced_display_names(self):
        import re

        self.assertIsNotNone(
            re.fullmatch(self.command_patterns["cmd_robbery"], "/打劫 @Alice Smith")
        )
        self.assertIsNotNone(
            re.fullmatch(self.command_patterns["cmd_lookup"], "/查询 @Alice Smith")
        )
        self.assertIsNotNone(
            re.fullmatch(self.command_patterns["cmd_unbind"], "/解绑 @Alice Smith")
        )
        self.assertIsNotNone(
            re.fullmatch(
                self.command_patterns["cmd_adjust_balance"],
                "/调整余额 @Alice Smith 10.5",
            )
        )
        self.assertIsNone(
            re.fullmatch(
                self.command_patterns["cmd_adjust_balance"],
                "/调整余额 @Alice Smith 10.5 extra",
            )
        )


if __name__ == "__main__":
    unittest.main()
