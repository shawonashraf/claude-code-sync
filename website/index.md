---
hide:
  - navigation
  - toc
---

<div class="ccs-hero" markdown>

# Your Claude Code setup, everywhere { .ccs-title }

Skills, plugins, hooks, and settings — backed up to a folder or git repo you
control, restored on any machine with one command. Never your chats, never
your secrets.

[Get started](getting-started.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/shawonashraf/claude-code-sync){ .md-button }

<div class="ccs-terminal">
<div class="ccs-terminal-bar"><span></span><span></span><span></span><em>zsh — your machine</em></div>
<pre><code><b>$ uvx claude-code-sync init ~/claude-backup --yes</b>
Note: if you back up from multiple machines to the same repo, their
histories can diverge. claude-code-sync never merges automatically — it
detects divergence and walks you through choosing which version to keep.
First backup: ok → /Users/you/claude-backup
Redacted from settings.json (never leaves this machine): ANTHROPIC_AUTH_TOKEN
<b>$ git -C ~/claude-backup log --oneline</b>
405e7ec claude-sync: yourmachine.local 2026-08-14T12:49:04Z</code></pre>
</div>

</div>

## What syncs — and what never does

The whole tool is built around this line. Configuration crosses machines;
everything personal stays where it is.

<div class="ccs-columns" markdown>

<div class="ccs-col ccs-col-yes" markdown>

### Synced

- `skills/` — your custom skills
- `hooks/` — your hook scripts
- `agents/` — your agent definitions
- `keybindings.json` and global `CLAUDE.md`
- `settings.json` — with secrets redacted first
- Plugin list — as a manifest, reinstalled on restore

</div>

<div class="ccs-col ccs-col-no" markdown>

### Never synced

- Chat history and transcripts
- Sessions and project data
- Credentials, API keys, tokens
- Plugin caches and downloads
- Shell snapshots, telemetry, IDE state

</div>

</div>

## Three steps, whole story

1. **Back up once.** `uvx claude-code-sync init` walks you through choosing a
   destination — a git repo gets a commit per change, a cloud-synced folder
   just mirrors.
2. **Forget about it.** A Claude Code session-end hook runs a quiet backup
   whenever your settings might have changed. No daemons, no schedulers.
3. **Restore anywhere.** On a new machine,
   `uvx claude-code-sync restore <your-repo-url>` brings back your skills,
   settings, and plugins — and prints a checklist of the env vars you need
   to re-supply by hand.

!!! tip "The installed command is `claude-sync`"
    `claude-code-sync` is the package name on PyPI; both `claude-sync` and
    `claude-code-sync` work as commands once installed. The docs use the
    package name in `uvx` examples so they work verbatim.

Ready? [Set up your first backup →](getting-started.md)
