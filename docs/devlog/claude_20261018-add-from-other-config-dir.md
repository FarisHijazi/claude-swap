# `add` from a non-default CLAUDE_CONFIG_DIR keeps the active slot

`cswap add` already captures whatever login `CLAUDE_CONFIG_DIR` names, which is
the documented way to store a second account's full login without switching
the default profile. Both write paths (the in-place credential refresh and the
new/explicit slot path) still set `activeAccountNumber` to the captured slot,
though, so the roster claimed an account was active while the default profile
held another. Plain rotation anchors on that field.

`_capture_is_live_store()` now gates both writes: the slot is marked active only
when `CLAUDE_CONFIG_DIR` is unset or resolves to the default profile (via the
existing `_same_directory`). Credential and config backups are written exactly
as before. Session-profile shells are still refused earlier by
`_refuse_session_shell`.

Caution for users: after such an add, the captured directory and cswap hold the
same rotating refresh grant. Retire the directory's copy (delete its
credential, do not `logout`, which revokes the grant server-side) so cswap's
consume gate is the only consumer.

Tests: `TestAddAccountSlot::test_add_from_other_config_dir_keeps_active_slot`
covers both paths. Full suite: 2,407 passed, 4 skipped.
