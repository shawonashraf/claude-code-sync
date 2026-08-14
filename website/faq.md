# FAQ & troubleshooting

## The hook doesn't seem to run

Backups happen when a Claude Code **session ends**, not continuously. Check
three things:

1. `claude-sync status` → "Session-end hook: installed".
2. The hook's command path exists: look for the `claude-sync backup --quiet`
   entry under `hooks.SessionEnd` in `~/.claude/settings.json`. If you
   installed via `uvx` without a persistent install, prefer
   `uv tool install claude-code-sync` and re-run `claude-sync hook install`
   so the hook points at a stable binary.
3. Remember unchanged state is invisible by design — end a session after
   actually changing a skill or setting, then check `git log` in your
   backup repo.

## `status` says CONFLICT PENDING

Two machines backed up divergent versions to the same repo. Nothing is
wrong and nothing was lost — the automatic backup just refused to guess.
Run:

```console
$ claude-sync resolve
```

and pick a side. The other version stays in git history. Details in
[Multi-machine](multi-machine.md).

## A plugin failed to reinstall after restore

Restore is fail-soft: every failure is listed with a retry command, e.g.

```text
FAILED plugin some-plugin@some-marketplace: …
  retry: claude plugin install some-plugin@some-marketplace
```

Common causes: the marketplace repo moved or requires auth, or the `claude`
CLI wasn't on PATH during restore (install Claude Code first, then rerun
the retry commands).

## "claude-sync is not configured"

Run `claude-sync init` on a fresh machine — or, if this machine should
adopt an existing backup, `claude-sync restore <url-or-path>`, which also
configures the destination for future backups.

## "destination must not be inside ~/.claude"

The guard that keeps a backup from overwriting the very settings it's
backing up. Choose any directory outside `~/.claude` — a dedicated
`~/claude-backup` repo is the usual choice.

## Backup exits silently and does nothing

That's success: nothing changed since the last sync. Force some output with
`claude-sync status` (shows drift) or make a change and back up again.

## Another run was already syncing

Two sessions ended at once; the second backup found the lock held and
exited 0. The next session end (or a manual `backup`) picks up anything the
skipped run would have synced.

## My env vars are empty after a restore

By design — secrets never travel. `claude-sync status` on the restored
machine lists every redacted env var; fill in their real values in
`~/.claude/settings.json`. See [Security & privacy](security.md).

## Where is my old configuration after a restore?

Every overwritten file was saved first:

```text
~/.claude-sync-backup-<timestamp>/
```

Copy anything back from there to undo a restore.
