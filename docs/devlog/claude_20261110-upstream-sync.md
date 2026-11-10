# Upstream sync — 2026-11-10

Merged upstream `5ac68bf` (190 commits, 0.28.0b1 → 1.1.0b1) into fork `4674e69`
(5 fork-only commits). 13 files conflicted. Fork maintenance rules are in
`AGENTS.md` ("Fork maintenance"); this file records the decisions.

## Probe overlap (owner decision)

Both sides grew a 1-output-token Haiku probe for credentials the usage endpoint
cannot answer.

- **Setup-tokens** (inference-only OAuth) now use upstream's header probe
  (`oauth.request_usage_via_probe`, opt-in `usage.headerProbe`). It reads the real
  5h/7d (and Fable weekly) utilization from `anthropic-ratelimit-unified-*`
  response headers, which beats our binary "Haiku available" observation. The
  fork's setup-token path is gone: `uses_availability_probe` is API-key only, and
  the autoswitch fallback that landed on an "available" setup-token was dropped.
- **API keys** keep the fork's binary availability probe
  (`try_probe_availability`, `usage.availabilityProbe`, default on). Upstream only
  shows "API key (no quota)": a key has no subscription windows, so its headers
  carry no percentages to read, and we never fabricate one.
- **One request shape.** The API-key probe now sends upstream's
  `USAGE_PROBE_MODEL` / `USAGE_PROBE_SYSTEM` / `USAGE_PROBE_API_VERSION` and the
  same `"hi"` message, authenticated with `x-api-key` instead of a bearer token.
  The model moved from `claude-haiku-4-5-20251001` to upstream's undated
  `claude-haiku-5-5`.

## Other resolutions

- `share_history` is upstream's `bool | None` request; `run` hands the request
  (not the answer) to `setup_session`, alongside `share_all`. `cswap env
  --share-history` now defaults to `None` too, so `run.shareHistory` decides.
- Share-all runs through upstream's `_sync_items`. Its `scope` default is now
  `None` = every manageable name (static lists + manifest + active share-all
  items), so links left by an earlier share-all launch are still removed when it
  is turned off. Removal still only unlinks for any non-`SHARED_ITEMS` name.
  `_DIR_ITEMS`/junctions are untouched; share-all stays refused on Windows.
- `_format_usage_lines` (now built on upstream's `_usage_rows`) returns the
  availability label early, as before.
- `UsageSettings` holds both `header_probe` and `availability_probe`; the config
  registry lists both (14 keys).
- `AGENTS.md`: upstream's agent guide plus a "Fork maintenance" section. README:
  upstream's layout; the availability section is now "Availability checks for
  API keys" and sits after the add-token limits.

## Validation

`uv sync --locked` ok. `uv run --locked pytest -q -n 8` under umask 022:
**3,618 passed, 12 skipped**. Under this box's umask 077 one upstream test,
`test_settings.py::TestAtomicWriteThroughSymlink::test_hardening_stays_on_the_directory_cswap_owns`,
fails because `mkdir(mode=0o755)` is masked to 0700. That's an environment issue,
not the merge. No live accounts, installs or network were used.
