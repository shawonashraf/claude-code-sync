# claude-code-sync

Back up and restore your Claude Code configuration — skills, hooks, agents,
keybindings, global CLAUDE.md, a redacted settings.json, and a plugin
manifest. Never your history, sessions, or projects.

Docs: https://shawonashraf.github.io/claude-code-sync/

## Quick start

Set up backups on the machine you already use:

    uvx claude-code-sync init

Reproduce your setup on a new machine (one command):

    uvx claude-code-sync restore https://github.com/you/claude-backup.git

The installed command is `claude-sync` (with `claude-code-sync` as an alias
— the PyPI name).

## Commands

| Command | What it does |
|---|---|
| `claude-sync init [dest]` | Interactive setup: choose destination, git mode, auto-backup hook |
| `claude-sync backup` | One sync pass (no-op when nothing changed; commits in git mode) |
| `claude-sync restore [src]` | Restore from a directory or git URL; reinstalls plugins |
| `claude-sync status` | Destination, last backup, drift, pending conflicts |
| `claude-sync resolve` | Choose a version when two machines diverged |
| `claude-sync hook install\|uninstall` | Manage the SessionEnd auto-backup hook |

## What about secrets?

Env vars in `settings.json` whose names look sensitive (`*KEY*`, `*TOKEN*`,
`*SECRET*`, `*PASSWORD*`, `*CREDENTIAL*`) or whose values look like
credentials are emptied (`""` — never a placeholder string, which Claude
Code would treat as a real credential) before anything leaves your machine.
`claude-sync status` lists what you need to re-supply after a restore.

## Multi-machine use

Backups from several machines to one git repo can diverge. claude-sync never
merges on its own: it detects divergence, skips the automatic backup, and
`claude-sync resolve` lets you pick which version to keep. The losing
version stays in git history.
