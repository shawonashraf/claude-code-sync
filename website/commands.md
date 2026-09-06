# Command reference

Seven commands. The installed binary is `claude-sync` (alias:
`claude-code-sync`); with `uvx`, use `uvx claude-code-sync <command>`.

---

## `init`

```console
$ claude-sync init [destination] [--yes] [--auto-push | --no-auto-push]
```

Interactive setup: choose a destination, decide git mode, optionally
install the session-end hook, then run the first backup.

| Argument / flag | Meaning |
|---|---|
| `destination` | Backup directory. Omit it to be prompted (default `~/claude-backup`). Created if missing. |
| `--yes` | Accept every default, no prompts: git mode on (initializing a repo if needed), hook installed. For scripts. |
| `--auto-push` / `--no-auto-push` | Push each backup commit to the remote. Default: on when the repo already has a remote (you are asked interactively), off otherwise. |

The destination may not be inside `~/.claude` (or contain it) — init
refuses with an error rather than risk your live settings.

---

## `backup`

```console
$ claude-sync backup [--quiet] [--show-redactions]
```

One sync pass. Unchanged state exits silently with no commit.

| Flag | Meaning |
|---|---|
| `--quiet` | Hook mode: no output except errors and warnings; never prompts. A detected conflict is skipped and flagged instead. |
| `--show-redactions` | Print which env vars were redacted from `settings.json`. |

Git-mode failures are never silent: a failed commit or push warns on
stderr while the backup itself still succeeds locally.

---

## `restore`

```console
$ claude-sync restore [source] [--to PATH] [--auto-push | --no-auto-push]
```

Bring a backup onto this machine and configure it for future backups.

| Argument / flag | Meaning |
|---|---|
| `source` | A git URL (`https://…`, `git@…`, `ssh://…`, `file://…`) or a local directory. Omit to restore from the already-configured destination. |
| `--to PATH` | Where to clone a URL source (default `~/claude-backup`). |
| `--auto-push` / `--no-auto-push` | Push each backup commit from this machine. Default: on when the source repo has a remote (always true for URL sources), off otherwise. |

Overwritten local files are saved to `~/.claude-sync-backup-<timestamp>/`
first. Plugin reinstalls are per-plugin fail-soft; failures are listed with
the exact retry command.

---

## `status`

```console
$ claude-sync status
```

Destination and mode, auto-push state (git mode only), last backup time,
whether local state differs from the backup, hook state, any pending
conflict, and the redacted-env re-supply checklist.

---

## `resolve`

```console
$ claude-sync resolve
```

Runs the interactive conflict flow when two machines' backups diverged:
keep this machine's version, keep the repo's version, or cancel. See
[Multi-machine](multi-machine.md).

---

## `config`

```console
$ claude-sync config
$ claude-sync config --auto-push
$ claude-sync config --no-auto-push
```

Print the destination, git mode, and auto-push state. With a flag, turn
auto-push on or off for future backups. Auto-push needs a git destination;
enabling it on a plain folder is refused.

---

## `hook`

```console
$ claude-sync hook install
$ claude-sync hook uninstall
```

Manage the Claude Code `SessionEnd` hook that runs `backup --quiet`
automatically. Install is idempotent; uninstall removes exactly this
tool's entry and touches nothing else. Both trigger a backup afterward so
the destination reflects the settings change.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success — including "nothing changed" and "another sync already running". |
| `1` | Actionable problem: not configured, pending conflict, bad destination, restore error, malformed config JSON, unreachable destination. The message on stderr says which. |
