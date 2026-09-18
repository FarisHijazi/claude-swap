# Upstream sync — 2026-09-18

Merged upstream `7187ce83b444c6af7b61ec8ee092623566a2d8fa` into fork
`ab9bd10c2881a3027e69a3b3cdab1f72b3b42eb7`: 189 incoming commits,
version 0.23.0b1 → 0.27.0b1 in [pyproject.toml](../../pyproject.toml).

## Integration

- Retained the fork's `cswap env` and `--share-all` behavior documented in
  [README.md](../../README.md).
- Resolved overlapping CLI flags and test doubles by passing both `share_all`
  and upstream's `require_session` option.
- Preserved upstream's session re-seeding safeguards, while also passing
  `seed_full_config=share_all` and retaining sharing on the reuse path in
  [session.py](../../src/claude_swap/session.py).

## Notable upstream changes

- Safer credential capture, refresh locking, identity checks, and recovery of
  tokens rotated by sessions; rejected live-session credentials wait for renewal.
- More resilient quota polling and automatic switching, including exhausted
  accounts, rate limits, concurrent fetches, and quota recovery.
- `run --require-session`, `list --token-status`, and `unclaimed` commands;
  macOS menu-bar login service management.
- JSON last-good usage, fetch errors/retry times, and login expiration.
- Windows file-replacement retries, symlink handling, terminal reply handling,
  and broader, parallel CI coverage.

## Validation

`uv sync --locked` succeeded. On macOS with Python 3.14.7,
`uv run --locked pytest -q -n 4` passed: 2,277 passed, 4 skipped.
Three upstream pytest fixture deprecation warnings remain. The full run includes
the fork's shell-export and share-all tests and upstream session safety tests.
No live account-switching or login operations were used for validation.
