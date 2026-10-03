# Backup & restore

What actually happens when claude-sync runs — so you can trust it with your
setup.

## What a backup does

Each `claude-sync backup` is one pass:

1. **Build the sync set in memory.** Your `skills/`, `hooks/`, and `agents/`
   directories, `keybindings.json`, global `CLAUDE.md`, a redacted copy of
   `settings.json`, and a generated `plugins-manifest.json`.
2. **Diff against the destination.** Nothing changed → the run exits
   silently. No commit, no timestamp churn, nothing to see.
3. **Mirror the changes.** New and changed files are written; files you
   deleted locally are deleted from the backup too, so an uninstalled skill
   doesn't come back from the dead on restore. Dot-prefixed files inside
   the mirrored directories (runtime state like a hook's `.state.json`)
   are skipped — they're machine state, not configuration.
4. **Commit (git mode).** One commit per changed backup:
   `claude-sync: <machine> <timestamp>`. With `auto_push` on, it's pushed
   immediately.

The destination looks like this:

```text
claude-backup/
├── claude-sync.meta.json    # tool version, last sync, source machine
├── plugins-manifest.json    # marketplaces + plugins, no cache content
├── settings.json            # redacted copy
├── keybindings.json
├── CLAUDE.md
├── skills/
├── hooks/
└── agents/
```

!!! info "Each OS keeps its own settings.json and hooks/"
    Those two hold absolute paths and shell scripts, so they only make sense
    on the OS that wrote them. Linux uses the repo root (as above); Windows
    and macOS use `windows/` and `macos/` subfolders holding their own
    `settings.json` and `hooks/`. Skills, agents, `CLAUDE.md`, keybindings and
    the plugin manifest stay shared. Each OS only ever writes — and deletes —
    its own subtree. Restoring on an OS with no variant yet keeps that
    machine's local settings/hooks; its first `claude-sync backup` creates them.

!!! info "Plugins travel as a manifest, not as files"
    Installed plugins are recorded as `name@marketplace` plus the
    marketplace's source — like a lockfile. Restore reinstalls them through
    the `claude` CLI instead of copying caches, so backups stay small and
    plugins arrive fresh for the new machine.

## Restore on a new machine

One command, from a git URL or a local directory:

```console
$ uvx claude-code-sync restore git@github.com:you/claude-backup.git
```

What it does, in order:

1. **Clones the repo** (shallow) to `~/claude-backup` — pick another spot
   with `--to <path>`. The clone becomes this machine's configured backup
   destination, so future backups flow to the same place.
2. **Saves a safety copy** of any local file it's about to overwrite, to
   `~/.claude-sync-backup-<timestamp>/`. Restoring is reversible.
3. **Copies your configuration in.** Backup wins for the files it carries;
   local files that aren't in the backup are left alone.
4. **Reinstalls plugins.** Marketplaces are re-added, then each plugin is
   installed via `claude plugin install`. One failure never aborts the rest
   — the summary lists exactly what failed and the command to retry.
5. **Prints your re-supply checklist:** the env vars that were redacted at
   backup time and need their real values entered on this machine.

```console
Restored 143 files.
Previous local files saved to /Users/you/.claude-sync-backup-20260814-125104
Re-supply these env vars in ~/.claude/settings.json: ANTHROPIC_AUTH_TOKEN
```

Already have a machine configured? Plain `claude-sync restore` (no URL)
restores from its configured destination.

Next: [what happens when two machines both back up →](multi-machine.md)
