# Security & privacy

You're trusting this tool with the directory that holds your Claude Code
life. Here is precisely what it reads, what it writes, and what it refuses
to carry.

## What never leaves your machine

claude-sync reads exactly seven things from `~/.claude`: `skills/`,
`hooks/`, `agents/`, `settings.json`, `keybindings.json`, `CLAUDE.md`, and
the two plugin index files. Everything else is never opened — not chat
history, not sessions, not project data, not shell snapshots, not
telemetry. This isn't a filter that could miss something; the code has no
path that touches those files at all.

## How secrets are redacted

`settings.json` is the one synced file that can contain secrets, in its
`env` block. Before a backup is written, every env var is checked two ways:

**By name** — case-insensitive match on `KEY`, `TOKEN`, `SECRET`,
`PASSWORD`, `CREDENTIAL` anywhere in the name.

**By value** — even when the name looks harmless:

- Known credential prefixes: `sk-`, `ghp_`, `gho_`, `github_pat_`,
  `glpat-`, `xox…-`, `AKIA`
- Long high-entropy strings (32+ mixed alphanumeric characters)
- JWTs (`eyJ…`-style dotted tokens)
- URLs with embedded passwords — `postgres://user:SECRET@host/db` is
  caught; `https://example.com/path` passes through

A matching value is replaced with the literal placeholder:

```json
{ "env": { "ANTHROPIC_AUTH_TOKEN": "<redacted-by-claude-sync>" } }
```

The placeholder is kept rather than dropped on purpose: after a restore,
`claude-sync status` reads the placeholders back and prints a checklist of
exactly which env vars you need to re-supply. Redaction happens in memory —
your local `settings.json` is never modified.

Want to see the filter's decisions? `claude-sync backup --show-redactions`
lists every redacted name.

## Guard rails

- **The destination can't be `~/.claude` itself** (or anything inside it, or
  anything containing it). Without this guard, a mistyped init could
  overwrite your live settings with the redacted copy.
- **Restore saves a safety copy first.** Every file it overwrites is copied
  to `~/.claude-sync-backup-<timestamp>/` before anything is written.
- **Backups never force-push, never pull, never merge silently.** The tool's
  git vocabulary is add, commit, push — plus the two explicit conflict
  resolutions you choose interactively.

## Honest limitations

- Redaction covers `settings.json`'s env block. Skills, hook scripts, and
  `CLAUDE.md` sync verbatim — if you hardcode a token inside a hook script,
  it will travel. Keep secrets in env vars, which is where the filter looks.
- The name heuristics are deliberately over-eager (a var named `MONKEY`
  gets redacted for containing `KEY`). Over-redaction fails safe: the value
  stays on your machine and shows up on the re-supply checklist.
- Restoring from a backup means trusting that backup: restored hook scripts
  and skills execute with your permissions. Restore only from repos you
  control.

Next: [every command and flag →](commands.md)
