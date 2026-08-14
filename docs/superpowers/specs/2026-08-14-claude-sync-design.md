# claude-sync — Design Spec

**Date:** 2026-08-14
**Status:** Approved design, pre-implementation

## Purpose

`claude-sync` backs up a user's Claude Code configuration to a directory of
their choice — a cloud-synced folder (Google Drive, Dropbox) or a git
repository — and restores it on a new machine with one command. The goal is a
reproducible Claude Code setup: install, restore, start working.

The tool syncs configuration only: skills, plugins (as a manifest), hooks,
agents, keybindings, global instructions, and a redacted `settings.json`.
It never touches history, sessions, projects, or any other usage data —
both for privacy and to stay clear of Anthropic ToS grey areas.

## Decisions (agreed during brainstorming)

| Question | Decision |
|---|---|
| Sync scope | Full config minus secrets (not just skills+plugins) |
| Plugin handling | Manifest + reinstall via `claude` CLI; never copy the cache |
| Trigger | Claude Code `SessionEnd` hook |
| Destination | Git-aware: auto-commit in git repos, plain mirror otherwise |
| Restore conflicts | Backup wins; a one-shot local safety copy makes it reversible |
| Distribution | PyPI, run via `uvx claude-sync` / `pipx` |
| Language / tooling | Python 3.13, `uv`, dependencies: `rich`, `questionary` |

## CLI Surface

One console script, `claude-sync`, with six subcommands: `init`, `backup`,
`restore`, `status`, `resolve`, and `hook`.

### `claude-sync init [<destination>]`

Interactive setup wizard (built with `rich` + `questionary`):

1. Welcome panel.
2. Destination path prompt with tab-completion (skipped if the argument was
   given). Creates the directory if missing.
3. Git detection. If the destination is a git repo: confirm "Treat this as a
   git-backed destination? Commits will be made automatically." If it is a
   plain folder: offer to `git init` it.
4. For git destinations, a plain-language note: "If you back up from multiple
   machines to the same repo, their histories can diverge. claude-sync never
   merges automatically — it detects divergence and walks you through choosing
   which version to keep."
5. Yes/no: install the SessionEnd hook.
6. Summary panel, then the first backup with a progress display, including
   `--show-redactions` output so the user sees what was filtered.

`--yes` (or a destination argument plus defaults) skips all prompts for
scripted use.

Configuration is written to `~/.claude-sync.json` — deliberately outside
`~/.claude` so the tool's own config is never part of the synced set. It
holds: destination path, git-mode flag (auto-detected, overridable),
`git.auto_push` (default `false`), `conflict_pending` flag, and last-run
timestamps. Never credentials.

### `claude-sync backup`

One sync pass: build the sync set in memory, mirror it to the destination,
update metadata, auto-commit if git-mode. Safe to run repeatedly: when
nothing changed it makes no commit, writes nothing, and exits 0 silently.

Flags: `--quiet` (hook mode: suppress all output except errors and conflict
warnings; enforce non-interactive behavior), `--show-redactions` (print what
was redacted from `settings.json`).

### `claude-sync restore [<source>]`

The new-machine command. `<source>` is a local directory or a git URL. A URL
is shallow-cloned to `--to <path>` (default `~/claude-backup`), and that
clone is written to `~/.claude-sync.json` as the destination — so a fresh
machine is set up for ongoing backups by the same command. A local directory
source is likewise recorded as the destination. With no argument, restores
from the already-configured destination.

Steps:

1. Save a safety copy of every local file about to be overwritten to
   `~/.claude-sync-backup-<timestamp>/`.
2. Copy synced files into `~/.claude` (backup wins; local-only files not in
   the backup are left alone).
3. Re-add marketplaces (`claude plugin marketplace add …`) and reinstall
   plugins (`claude plugin install name@marketplace`) from
   `plugins-manifest.json`. Per-plugin fail-soft: one failure does not abort
   the rest.
4. Print a summary: what was restored, which plugin installs failed (with the
   exact command to retry), and a checklist of redacted env vars the user
   must re-supply.

### `claude-sync resolve`

Runs the interactive git-conflict flow (see Git Conflict Handling) without
performing a backup. Exists so a hook-flagged `conflict_pending` can be
cleared directly; a manual `backup` reaches the same prompt.

### `claude-sync status`

Shows: destination and mode, last backup time, whether local state differs
from the backup, hook installation state, pending conflicts, and the redacted
env-var checklist.

### `claude-sync hook install|uninstall`

Manages the SessionEnd hook entry in `~/.claude/settings.json` (see Hook
section).

## Sync Set and Destination Layout

```
<destination>/
  claude-sync.meta.json       # tool version, schema version, last sync time, source machine
  plugins-manifest.json       # generated: marketplaces + installed plugins
  settings.json               # redacted copy
  keybindings.json            # if present
  CLAUDE.md                   # global instructions, if present
  skills/                     # mirror of ~/.claude/skills/
  hooks/                      # mirror of ~/.claude/hooks/
  agents/                     # mirror of ~/.claude/agents/, if present
```

`plugins-manifest.json` is distilled from `~/.claude/plugins/installed_plugins.json`
and `~/.claude/plugins/known_marketplaces.json`: for each marketplace its
source (e.g. `github: anthropics/claude-plugins-official`); for each plugin
`name@marketplace`, version, and scope. Machine-specific fields
(`installPath`, local timestamps) are dropped. Plugin cache content is never
copied.

Mirroring is true mirroring: files deleted locally since the last backup are
deleted from the destination, so an uninstalled skill does not resurrect on
restore. Exception: entries in `skills/` or `hooks/` that are symlinks into
the plugin cache are recorded in the manifest, not followed — restoring the
plugin recreates them.

Everything else in `~/.claude` — history, projects, sessions, shell
snapshots, file-history, daemon state, telemetry, IDE locks — is never read
or copied.

## Redaction of `settings.json`

`settings.json` is the only synced file that can contain secrets. Observed
top-level keys: `env`, `permissions`, `model`, `hooks`, `enabledPlugins`,
`extraKnownMarketplaces`.

- **`env` is the danger zone.** Each entry is tested against a deny-pattern
  list on the name (`*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`,
  `*CREDENTIAL*`, case-insensitive) and a value heuristic (known credential
  shapes such as `sk-…` prefixes and long high-entropy strings). Matching
  values are replaced with the literal string `"<redacted-by-claude-sync>"`.
  The placeholder is kept, not dropped, so restore can print a checklist of
  env vars the user must re-supply.
- All other keys pass through unchanged — they are the reproducible config
  this tool exists to carry.
- Redaction happens in memory during backup; the local file is never
  modified. Restore writes placeholders as-is: Claude Code treats them as
  ordinary strings, nothing breaks, and the checklist tells the user what to
  fill in.
- `backup --show-redactions` (and the init summary) prints what was redacted
  so the user can verify the filter in both directions.

Out of scope entirely: `settings.local.json` and project-level `.claude/`
directories. This tool syncs user-global config only.

## Backup Flow

1. Read `~/.claude-sync.json`; acquire `~/.claude-sync.lock` (a second
   overlapping run exits immediately — two Claude sessions can end at once).
2. Git mode only: pre-sync conflict check (next section). A pending conflict
   stops the backup.
3. Build the sync set in memory (mirror trees, generated manifest, redacted
   settings).
4. Diff against the destination file-by-file: size + mtime, content hash on
   mismatch. No differences → release lock, exit 0 silently.
5. Write changed files, delete stale ones, update `claude-sync.meta.json`.
6. Git mode: `git add -A && git commit -m "claude-sync: <machine> <timestamp>"`.
   If `git.auto_push` is true, push; a failed push warns but never fails the
   backup — the commit is safe locally.

The tool never pulls, merges, or force-pushes.

## Git Conflict Handling

Before mirroring, in git mode, `backup` checks the destination repo for:

- unmerged (conflicted) files — the user pulled and git stopped mid-merge, or
- divergence: local and remote both have new commits, checked against the
  already-fetched remote ref. The tool never fetches on its own.

**Interactive** (manual `backup`, `init`, or `claude-sync resolve`): a
two-option prompt —

> Your backup has two conflicting versions: this machine's and the one in the
> repo. Keeping one loses the other from the working copy — the losing
> version stays in git history.

- **Keep this machine's version:** resolve the merge to a clean state,
  overwrite with a fresh mirror of this machine's settings, commit.
- **Keep the repo's version:** resolve in favor of the repo's version,
  commit, skip this backup, and offer to run `restore` immediately so this
  machine adopts it.

**Non-interactive** (`--quiet`, hook-triggered): never prompt, never guess.
Skip the sync, leave the repo untouched, set `conflict_pending` in
`~/.claude-sync.json`, and emit a one-line warning so the skipped sync shows
in the session transcript. `status` displays the pending conflict
prominently; the next interactive `backup` or `claude-sync resolve` runs the
prompt above.

## SessionEnd Hook

`claude-sync hook install` adds a `SessionEnd` hook entry to
`~/.claude/settings.json` running `claude-sync backup --quiet`. Properties:

- Idempotent: installing twice yields one entry.
- Uninstall removes exactly our entry and nothing else.
- Because the hook edits the very file being backed up, install and uninstall
  each trigger a backup afterward so the destination reflects the change.
- The hook command uses the resolved absolute path to `claude-sync` (or
  `uvx claude-sync`) so it works regardless of shell PATH at hook time.

## Error Handling

- Every failure mode — missing `claude` CLI on restore, unreachable
  destination, git errors, malformed JSON under `~/.claude` — produces a
  one-line actionable message.
- `backup` never leaves the destination half-written: a write pass ends with
  either the trailing commit or an explicit warning.
- Restore's plugin reinstalls are fail-soft per plugin; the summary lists
  failures with the exact retry command.

## Testing

- pytest, developed test-first (TDD).
- Densest coverage on redaction — the security-critical unit — then manifest
  generation, mirror/diff logic, and conflict detection. All run against
  fixture `~/.claude` trees in temp directories.
- Git behavior is tested against real throwaway repos in temp directories.
- The wizard's logic is separated from its prompts so every flow is testable
  without a TTY.

## Out of Scope

- Syncing history, sessions, projects, or any usage data.
- Bidirectional or continuous sync; the model is one-way backup plus explicit
  restore.
- Automatic pull, merge, or force-push in the destination repo.
- Project-level `.claude/` directories and `settings.local.json`.
- Windows support in v1 (macOS and Linux first; nothing in the design
  precludes it later).
