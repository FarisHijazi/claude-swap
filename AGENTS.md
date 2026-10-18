# Fork maintenance

This fork retains `cswap env` and `cswap run --share-all`; see the
[shell-pinning documentation](README.md#pin-a-whole-shell-to-an-account-cswap-env).
Preserve both alongside upstream session and credential-safety changes.

Key availability belongs to the existing OAuth transport and usage-store
collector, not a separate polling service. Preserve its shared claims, 120-second
probe floor, Retry-After, and unknown-on-error behavior. Binary Haiku observations
must never become fabricated utilization percentages; see
[the availability contract](README.md#availability-checks-for-keys) and
`tests/availability_probe_test.py`.

Run `uv sync --locked` and `uv run --locked pytest -q` before publishing changes.
Tests isolate account storage; do not substitute live account-switching commands.

Merge records use deliberately plain paths, not `@` includes:
`docs/devlog/claude_20260918-upstream-sync.md`.
`docs/devlog/claude_20261018-key-availability-probes.md`.
