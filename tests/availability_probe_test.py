"""Availability observations: real request contract, shared cadence and decisions."""

from __future__ import annotations

import io
import json
import urllib.error
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

import pytest

from claude_swap import oauth
from claude_swap.autoswitch import NoSwitchEvent, TickOutcome
from claude_swap.json_output import usage_from_json, usage_to_json
from claude_swap.menubar import _account_display_usage
from claude_swap.settings import load_usage_settings, set_setting
from claude_swap.switcher import _usage_entry_lines
from claude_swap.usage_store import FetchRecord, UsageEntry, UsageStore
from tests.test_api_key_accounts import API_KEY, _linux_switcher
from tests.test_autoswitch import EngineHarness, FakeClock, _usage
from tests.test_tui import make_account
from claude_swap.tui.widgets import account_card_text, mini_account_text


def observation(status="available", **extra):
    return {"availability": {
        "status": status, "model": oauth.USAGE_PROBE_MODEL,
        "source": "haiku_probe", **extra,
    }}


def setup_credentials():
    return json.dumps({"claudeAiOauth": {
        "accessToken": "sk-ant-oat01-example", "scopes": ["user:inference"],
    }})


def response(payload=None):
    result = MagicMock()
    result.__enter__.return_value.read.return_value = json.dumps(
        {"type": "message", "content": [{"type": "text", "text": "."}]}
        if payload is None else payload
    ).encode()
    return result


def http_error(code, *, message="request failed", retry=None):
    headers = Message()
    if retry is not None:
        headers["Retry-After"] = str(retry)
    return urllib.error.HTTPError(
        oauth.USAGE_PROBE_URL, code, "error", headers,
        io.BytesIO(json.dumps({"error": {"message": message}}).encode()),
    )


@pytest.mark.parametrize("credentials,is_key", [(API_KEY, True), (setup_credentials(), False)])
def test_probe_sends_one_real_minimal_haiku_request(credentials, is_key):
    with patch.object(oauth.urllib.request, "urlopen", return_value=response()) as send:
        outcome = oauth.try_probe_availability(credentials)
    assert outcome.error is None
    assert outcome.usage == observation()
    request = send.call_args.args[0]
    body = json.loads(request.data)
    assert body["model"] == oauth.USAGE_PROBE_MODEL
    assert body["max_tokens"] == 1
    assert body["messages"] == [{"role": "user", "content": "."}]
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert request.method == "POST"
    if is_key:
        assert request.get_header("X-api-key") == credentials
        assert request.get_header("Authorization") is None
        assert "system" not in body
    else:
        assert request.get_header("Authorization") == "Bearer sk-ant-oat01-example"
        assert request.get_header("Anthropic-beta") == oauth.OAUTH_BETA_HEADER
        assert body["system"] == oauth.USAGE_PROBE_SYSTEM
    assert send.call_count == 1
    assert "text" not in json.dumps(outcome.usage)
    assert oauth.account_headroom(outcome.usage) is None
    assert oauth.relevant_windows(outcome.usage) == []


@pytest.mark.parametrize("error,expected", [
    (http_error(429, retry=420), "rate_limited"),
    (http_error(400, message="Your credit balance is too low to access the API"), "exhausted"),
])
def test_only_explicit_inference_limit_is_blocked(error, expected):
    with patch.object(oauth.urllib.request, "urlopen", side_effect=error):
        outcome = oauth.try_probe_availability(API_KEY)
    assert oauth.availability_status(outcome.usage) == expected
    assert outcome.error is None
    if expected == "rate_limited":
        assert outcome.usage["availability"]["retryAfterSeconds"] == 420


@pytest.mark.parametrize("error,expected", [
    (http_error(401), "http-401"), (http_error(403), "http-403"),
    (http_error(404), "http-404"), (http_error(400), "http-400"),
    (http_error(500), "http-500"), (TimeoutError(), "timeout"),
    (urllib.error.URLError("unreachable"), "network"),
])
def test_auth_model_and_transport_failures_never_mean_exhausted(error, expected):
    with patch.object(oauth.urllib.request, "urlopen", side_effect=error):
        outcome = oauth.try_probe_availability(API_KEY)
    assert outcome.usage is None
    assert outcome.error == expected


def test_probe_does_not_treat_non_message_200_as_available():
    with patch.object(oauth.urllib.request, "urlopen", return_value=response({"error": "upstream unavailable"})):
        outcome = oauth.try_probe_availability(API_KEY)
    assert outcome == oauth.UsageOutcome(None, error="bad-response")


@pytest.mark.parametrize("credentials,eligible", [
    (API_KEY, True), (setup_credentials(), True),
    (json.dumps({"claudeAiOauth": {"accessToken": "token", "refreshToken": "refresh", "scopes": ["user:profile", "user:inference"]}}), False),
    (json.dumps({"claudeAiOauth": {"accessToken": "token"}}), False),
    ("", False),
])
def test_probe_eligibility_preserves_full_oauth_usage(credentials, eligible):
    assert oauth.uses_availability_probe(credentials) is eligible


def test_success_error_and_missed_probe_decision_freshness():
    entry = UsageEntry(last_good=observation(), age_s=1, fetched_at=1000)
    assert entry.decision_value() == observation()
    assert replace(entry, age_s=121, trust_extended=True).decision_value() is None
    assert replace(entry, last_error="network").decision_value() is None


def test_collectors_share_120_second_cadence_and_never_refresh_tokens(temp_home):
    first = _linux_switcher()
    second = _linux_switcher()
    clock = FakeClock()
    first._usage_store.clock = second._usage_store.clock = clock
    info = [(2, "user@example.com", "", "", False, setup_credentials(), "")]
    with (
        patch.object(oauth, "try_probe_availability", return_value=oauth.UsageOutcome(observation())) as probe,
        patch.object(oauth, "try_fetch_usage_for_account") as usage,
        patch.object(first, "consume_backup_grant") as refresh,
    ):
        entry = first._collect_usage_entries(info)["2"]
        assert entry.next_poll_at == clock.now + 120
        assert entry.poll_interval_s == 120
        second._collect_usage_entries(info)
        clock.advance(119)
        first._collect_usage_entries(info)
        assert probe.call_count == 1
        clock.advance(1)
        second._collect_usage_entries(info)
        assert probe.call_count == 2
    usage.assert_not_called()
    refresh.assert_not_called()


def test_pending_claim_prevents_duplicate_probe(temp_home):
    switcher = _linux_switcher()
    info = [(2, "user@example.com", "", "", False, API_KEY, "")]
    identity = {"2": ("user@example.com", "")}
    claim = switcher._usage_store.reserve(["2"], identity, respect_plans=True)
    with patch.object(oauth, "try_probe_availability") as probe:
        switcher._collect_usage_entries(info)
    assert claim
    probe.assert_not_called()


def test_probe_retry_after_beats_normal_schedule(temp_home):
    switcher = _linux_switcher()
    clock = FakeClock()
    switcher._usage_store.clock = clock
    info = [(2, "user@example.com", "", "", False, API_KEY, "")]
    limited = observation("rate_limited", retryAfterSeconds=7200)
    with patch.object(oauth, "try_probe_availability", return_value=oauth.UsageOutcome(limited)) as probe:
        entry = switcher._collect_usage_entries(info)["2"]
        assert entry.next_poll_at == clock.now + 7200
        clock.advance(121)
        assert switcher._collect_usage_entries(info)["2"].decision_value() is None
        # Auto escalation and activating the slot cannot bypass Retry-After.
        switcher._replan_new_active("2", "user@example.com", "")
        switcher._collect_usage_entries(info, fetch={"2"})
        clock.advance(500)
        switcher._collect_usage_entries(info, fetch={"2"}, scheduled=True)
        assert probe.call_count == 1


def test_failed_probe_uses_shared_backoff_and_turns_old_success_unknown(temp_home):
    switcher = _linux_switcher()
    clock = FakeClock()
    switcher._usage_store.clock = clock
    info = [(2, "user@example.com", "", "", False, API_KEY, "")]
    with patch.object(oauth, "try_probe_availability", side_effect=[
        oauth.UsageOutcome(observation()), oauth.UsageOutcome(None, error="network"),
    ]) as probe:
        switcher._collect_usage_entries(info)
        clock.advance(120)
        entry = switcher._collect_usage_entries(info)["2"]
        assert entry.last_good == observation()
        assert entry.decision_value() is None
        assert entry.backoff_until == clock.now + 120
        clock.advance(60)
        switcher._collect_usage_entries(info)
        assert probe.call_count == 2


def test_http_date_retry_after_and_nonfinite_values():
    deadline = datetime.now(timezone.utc) + timedelta(seconds=300)
    _, retry = oauth._classify_usage_error(http_error(429, retry=format_datetime(deadline, usegmt=True)))
    assert 298 <= retry <= 300
    assert oauth._classify_usage_error(http_error(429, retry="inf"))[1] is None


def test_probe_failure_honors_long_retry_after(tmp_path):
    store = UsageStore(tmp_path / "cache", clock=lambda: 1000)
    identities = {"1": ("user@example.com", "")}
    store.record({"1": FetchRecord(error="http-503", retry_after_s=9000, probe=True)}, identities)
    assert store.entries(identities)["1"].backoff_until == 10000


def test_binary_json_round_trip_has_no_fabricated_percentage():
    value = observation("rate_limited", retryAfterSeconds=120)
    assert usage_from_json(usage_to_json(value)) == value
    assert "pct" not in json.dumps(usage_to_json(value))


@pytest.mark.parametrize("value", [
    {"status": "ready", "model": "haiku", "source": "haiku_probe"},
    {"status": "available", "model": 2, "source": "haiku_probe"},
    {"status": "available", "model": "haiku", "source": "haiku_probe", "retryAfterSeconds": -1},
])
def test_import_rejects_invalid_availability(value):
    with pytest.raises(ValueError, match="availability"):
        usage_from_json({"availability": value})


def test_ui_cli_and_menubar_render_binary_without_bars():
    entry = UsageEntry(last_good=observation(), fetched_at=1000, age_s=1)
    account = make_account(1, entry=entry)
    assert "Haiku available" in " ".join(_usage_entry_lines(entry))
    assert "Haiku available" in _account_display_usage(entry)
    for text in (
        account_card_text(account, 100, now=1001), mini_account_text(account, 1001),
    ):
        rendered = text.plain
        assert "Haiku available" in rendered
        assert "0%" not in rendered
    failed = replace(entry, last_error="http-401")
    assert "unknown" in " ".join(_usage_entry_lines(failed))
    assert "unknown" in _account_display_usage(failed)


def test_available_active_does_not_fail_over_for_missing_percentage(temp_home):
    harness = EngineHarness(temp_home)
    harness.seed(1, "user@example.com")
    harness.make_live("user@example.com", 1)
    for _ in range(4):
        assert harness.tick_with_usage({"1": observation()}) is TickOutcome.NO_ACTION
    assert any(isinstance(event, NoSwitchEvent) and event.reason == "haiku-available" for event in harness.events)


def test_haiku_success_does_not_assert_configured_opus_capacity(temp_home):
    harness = EngineHarness(temp_home, model="Opus")
    harness.seed(1, "user@example.com")
    harness.make_live("user@example.com", 1)
    harness.tick_with_usage({"1": observation()})
    assert not any(isinstance(event, NoSwitchEvent) and event.reason == "haiku-available" for event in harness.events)


def test_blocked_active_probe_fails_over_without_numeric_utilization(temp_home):
    harness = EngineHarness(temp_home)
    harness.seed(1, "user@example.com")
    harness.seed(2, "work@example.com")
    harness.make_live("user@example.com", 1)
    assert harness.tick_with_usage({"1": observation("rate_limited"), "2": _usage(20)}) is TickOutcome.SWITCHED
    assert harness.active_number() == 2


def test_setup_probe_is_failover_fallback_after_measured_accounts(temp_home):
    harness = EngineHarness(temp_home)
    harness.seed(1, "user@example.com")
    harness.seed(2, "work@example.com")
    harness.make_live("user@example.com", 1)
    assert harness.tick_with_usage({"1": _usage(100), "2": observation()}) is TickOutcome.SWITCHED
    assert harness.active_number() == 2


@pytest.mark.parametrize("candidate", [observation("rate_limited"), observation("exhausted"), None])
def test_auto_never_selects_rejected_or_unverified_api_key(temp_home, candidate):
    harness = EngineHarness(temp_home, include_api_key_accounts=True)
    harness.seed(1, "user@example.com")
    harness.seed(2, "work@example.com")
    harness.make_live("user@example.com", 1)
    data = harness.switcher._get_sequence_data()
    data["accounts"]["2"]["kind"] = "api_key"
    harness.switcher._write_json(harness.switcher.sequence_file, data)
    outcome = harness.tick_with_usage({"1": _usage(100), "2": candidate})
    assert outcome is not TickOutcome.SWITCHED
    assert harness.active_number() == 1


def test_probe_can_be_disabled_without_any_network(temp_home):
    switcher = _linux_switcher()
    set_setting(switcher.backup_dir, "usage.availabilityProbe", "false")
    assert load_usage_settings(switcher.backup_dir).availability_probe is False
    info = [(2, "user@example.com", "", "", False, API_KEY, "")]
    with patch.object(oauth, "try_probe_availability") as probe:
        entry = switcher._collect_usage_entries(info)["2"]
    assert entry.sentinel == "availability probe disabled"
    probe.assert_not_called()
