# Key availability probes — 2026-10-18

The user-facing behavior and cost/limitations are documented in
[README.md](../../README.md#availability-checks-for-keys). Maintenance ownership
is recorded in [AGENTS.md](../../AGENTS.md); paths in that index are deliberately
plain paths, not `@` includes.

## Existing implementation and research

Merged upstream `main` through `8fdc89a` onto the current fork `main`
(`b86e5ae`). The merge was conflict-free and preserves `cswap env` and
`cswap run --share-all`. Before the feature, the merged baseline passed
2,369 tests with 4 skipped; an independent review passed 342 session/CLI tests.

The existing collector, fenced fetch leases, disk cache and poll plans in
[switcher.py](../../src/claude_swap/switcher.py) and
[usage_store.py](../../src/claude_swap/usage_store.py) remain the only polling
owners. No second timer or background service was added. The TUI already runs a
fetch-enabled snapshot every three seconds through
[SnapshotSource](../../src/claude_swap/snapshot_source.py); eligibility is decided
under the usage-store lock. One-shot CLI commands use the same collector.

Reviewed upstream [issue 220](https://github.com/realiti4/claude-swap/issues/220),
[pull request 412](https://github.com/realiti4/claude-swap/pull/412) and
[pull request 229](https://github.com/realiti4/claude-swap/pull/229). Their proposed
header-percentage fallback does not cover API-key binary availability. Reused
the setup-token request contract verified in pull request 412: Haiku, one output
token, OAuth beta header and the required Claude Code system prompt. API-key
requests use `x-api-key` and omit that system prompt. The
[Messages API contract](https://platform.claude.com/docs/en/api/messages/create)
also supports zero output tokens for cache-only use; this feature intentionally
requests one generated token to check a real inference call.

## Implementation

- [oauth.py](../../src/claude_swap/oauth.py) owns the bounded request and response
  classification. Explicit inference-only OAuth scopes and managed API keys use
  probes; normal OAuth logins keep the richer usage endpoint. Authentication,
  model access and transport errors never imply exhausted credits. A 429 is
  labeled rate limited; only an explicit insufficient-credit error is exhausted.
- Binary observations live in `lastGood.availability`, with no fabricated quota
  windows or numeric headroom. Existing JSON freshness, error and last-good
  history fields still apply. CLI, TUI and menu bar display the observation.
- [poll_policy.py](../../src/claude_swap/poll_policy.py) defines the normal
  120-second probe interval. Shared leases suppress concurrent UI requests.
  Retry-After, including HTTP-date form, can extend the deadline; escalation,
  obsolete-plan repair and account role changes cannot shorten it. Probe errors
  wait at least 120 seconds. Successful observations become unknown after the
  next due probe is missed or any subsequent fetch fails.
- [settings.py](../../src/claude_swap/settings.py) exposes
  `usage.availabilityProbe` (default true). Turning it off suppresses network
  probes immediately without replacing existing cache history.
- [autoswitch.py](../../src/claude_swap/autoswitch.py) keeps a successful active
  probe healthy without inventing a utilization percentage. Fresh successful
  setup-token probes are failover fallbacks after measured headroom. Paid API
  keys still require the existing explicit opt-in and now also require a fresh
  successful probe. Haiku-only evidence is not used for configured per-model
  quota comparisons. `next-available` skips currently blocked probe results.

## Validation

`uv sync --locked` was run before implementation. A complete isolated run with
`uv run --locked pytest -q -n 8` passed **2,406 tests, 4 skipped** in 20.66
seconds, with three existing pytest fixture deprecation warnings. The focused
availability/autoswitch suite also passed (298 tests). `git diff --check` passed.

[availability_probe_test.py](../../tests/availability_probe_test.py) exercises
request size/authentication, correct failure classification, binary JSON,
display, cache freshness, multiple collectors, claim contention, 120-second
pacing, long Retry-After under escalation/role changes, opt-out and autoswitch.
Tests use existing isolated home/store fixtures and mock network transport.

A single real request against a saved inference-only OAuth setup-token returned
`availability.status: available` for `claude-haiku-4-5-20251001`. The credential
was read directly through the credential store; it was not refreshed. No live
account switching or writes to the user's Claude configuration were used.

Final independent review found no high-severity issues; 37 probe tests and
376 related regression tests passed separately.
