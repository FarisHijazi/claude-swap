# Fork maintenance

This fork retains `cswap env` and `cswap run --share-all`; see the
[shell-pinning documentation](README.md#pin-a-whole-shell-to-an-account-cswap-env).
Preserve both alongside upstream session and credential-safety changes.

Run `uv sync --locked` and `uv run --locked pytest -q` before publishing changes.
Tests isolate account storage; do not substitute live account-switching commands.

Merge records use deliberately plain paths, not `@` includes:
`docs/devlog/claude_20260918-upstream-sync.md`.
