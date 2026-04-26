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
