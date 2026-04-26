"""Tests for resolve_channel_prompt's composite-key disambiguation.

Sits next to test_discord_channel_prompts.py for discoverability — both
files are about channel_prompts resolution. Resolver itself lives in
gateway/platforms/base.py and is shared across Discord, Telegram,
Slack, and Mattermost.
"""

from gateway.platforms.base import resolve_channel_prompt


class TestResolveChannelPromptComposite:
    def test_composite_key_match(self):
        extra = {"channel_prompts": {"-1001:5": "Invoices in Group A"}}
        assert resolve_channel_prompt(extra, "5", "-1001") == "Invoices in Group A"

    def test_composite_key_disambiguates_colliding_threads(self):
        # #13256 repro: same thread_id exists in both supergroups.
        extra = {
            "channel_prompts": {
                "-1001:5": "Group A invoices",
                "-1002:5": "Group B backend",
            }
        }
        assert resolve_channel_prompt(extra, "5", "-1001") == "Group A invoices"
        assert resolve_channel_prompt(extra, "5", "-1002") == "Group B backend"

    def test_composite_preferred_over_channel_only(self):
        extra = {
            "channel_prompts": {
                "-1001:5": "Scoped prompt",
                "5": "Generic thread-5 prompt",
            }
        }
        assert resolve_channel_prompt(extra, "5", "-1001") == "Scoped prompt"

    def test_composite_preferred_over_parent_only(self):
        extra = {
            "channel_prompts": {
                "-1001:5": "Scoped prompt",
                "-1001": "Group-level prompt",
            }
        }
        assert resolve_channel_prompt(extra, "5", "-1001") == "Scoped prompt"

    def test_falls_back_to_channel_when_no_composite(self):
        # Backward compat: pre-#13256 configs with only thread-level keys
        # still resolve.
        extra = {"channel_prompts": {"5": "Thread prompt"}}
        assert resolve_channel_prompt(extra, "5", "-1001") == "Thread prompt"

    def test_falls_back_to_parent_when_no_composite_or_channel(self):
        extra = {"channel_prompts": {"-1001": "Group prompt"}}
        assert resolve_channel_prompt(extra, "5", "-1001") == "Group prompt"

    def test_composite_not_constructed_without_parent(self):
        # Pins that a stray ``:5`` key in config cannot match when no parent
        # is provided — the composite candidate must be None, not ":5".
        extra = {"channel_prompts": {":5": "Malformed", "5": "Channel prompt"}}
        assert resolve_channel_prompt(extra, "5") == "Channel prompt"

    def test_blank_composite_value_falls_through(self):
        # Blank prompt at the composite key must not short-circuit lookup —
        # resolver continues to the next-most-specific candidate.
        extra = {
            "channel_prompts": {
                "-1001:5": "   ",
                "5": "Thread prompt",
            }
        }
        assert resolve_channel_prompt(extra, "5", "-1001") == "Thread prompt"

    def test_int_typed_yaml_keys_match_after_config_bridging(self):
        """gateway/config.py:589-594 stringifies flat channel_prompts keys at config-bridge
        time. This test asserts the composite-key lookup behaves the same way after the
        bridge runs: post-bridge, all keys (including the composite one) are strings, so
        the resolver finds them. A pre-bridge dict with int keys is intentionally left as
        the bridge's responsibility (mirrors test_numeric_yaml_keys_normalized_at_config_load
        in test_discord_channel_prompts.py)."""

        # Post-bridging state — keys already stringified.
        extra_post = {"channel_prompts": {"-1001:5": "Composite", "-1001": "Group", "5": "Thread"}}
        assert resolve_channel_prompt(extra_post, "5", "-1001") == "Composite"

        # Pre-bridging state — int keys do not match. The bridge is responsible for
        # stringifying them. This test pins that the resolver itself does not silently
        # accept int keys, which would mask a bridge regression.
        extra_pre = {"channel_prompts": {-1001: "Group", 5: "Thread"}}
        assert resolve_channel_prompt(extra_pre, "5", "-1001") is None


class TestTelegramCallerContractCompositeKey:
    """Caller-contract test: replicates the exact (channel_id, parent_id) arg
    shape that gateway/platforms/telegram.py:_event_from_message passes to
    resolve_channel_prompt today, and verifies it reaches the composite-key
    path correctly. This is *not* a full integration test — it does not drive
    a fake telegram.Message through _event_from_message. The full path is
    exercised by the existing telegram-suite tests once the call-site change
    lands."""

    def _telegram_call(self, extra: dict, chat_id: str, thread_id: str | None) -> str | None:
        # Replicate the exact arg shape telegram.py passes today, line for line.
        return resolve_channel_prompt(
            extra,
            thread_id or chat_id,
            chat_id if thread_id else None,
        )

    def test_telegram_caller_resolves_composite_key(self):
        extra = {
            "channel_prompts": {
                "-1003742888118:5": "AI Villa ops",
                "-1003953149701:5": "Design ai-villa",
            }
        }
        assert self._telegram_call(extra, "-1003742888118", "5") == "AI Villa ops"
        assert self._telegram_call(extra, "-1003953149701", "5") == "Design ai-villa"

    def test_telegram_caller_falls_through_to_thread_key(self):
        extra = {"channel_prompts": {"5": "Generic thread 5"}}
        assert self._telegram_call(extra, "-1003742888118", "5") == "Generic thread 5"

    def test_telegram_caller_falls_through_to_chat_key_when_no_thread(self):
        # DM or non-forum group: thread_id is None; only the chat-level key applies.
        extra = {"channel_prompts": {"-1003742888118": "Group prompt"}}
        assert self._telegram_call(extra, "-1003742888118", None) == "Group prompt"
