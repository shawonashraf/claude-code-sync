# Getting started

By the end of this page your Claude Code configuration is backed up and
keeps itself backed up. Takes about two minutes.

## Install

Nothing to install permanently — `uvx` runs the latest release directly.
If you prefer a persistent install, use `uv tool` or `pipx`:

=== "uvx (no install)"

    ```console
    $ uvx claude-code-sync --help
    ```

=== "uv tool"

    ```console
    $ uv tool install claude-code-sync
    $ claude-sync --help
    ```

=== "pipx"

    ```console
    $ pipx install claude-code-sync
    $ claude-sync --help
    ```

!!! note
    A persistent install (`uv tool` / `pipx`) is recommended if you enable
    the auto-backup hook: the hook then calls a stable binary path instead
    of resolving the package on every session end.

## Or let Claude Code set it up

Prefer not to run the steps yourself? Paste this prompt into a Claude Code
session and it will clone the project, install it, and walk you through
`init`, asking you about each choice along the way:

```text
Clone the repo from https://github.com/shawonashraf/claude-code-sync which contains a sync tool for claude code and set it up on my computer. Ask questions about any choices you may have to make, such as directories, symlinks etc.
```

The rest of this page describes what it will ask, so you know what to
answer.

## Set up your first backup

Run init and answer its questions:

```console
$ claude-sync init
```

The wizard walks you through four decisions:

1. **Where do backups go?** Any directory works. Two setups make sense:
   a **git repository** (best: every backup is a commit, and you can push it
   to GitHub for off-machine safety) or a **cloud-synced folder** like Google
   Drive or Dropbox (the storage handles versioning).
2. **Treat it as git?** If the destination is already a git repo, claude-sync
   auto-commits each backup. If it's a plain folder, the wizard offers to
   `git init` it for you.
3. **Install the session-end hook?** Say yes for hands-off operation — every
   time a Claude Code session ends, a quiet backup runs and syncs any
   changes.
4. **First backup runs.** You'll see exactly which env vars were redacted
   from `settings.json` before anything was written.

Scripting it? Skip all prompts with defaults (git mode on, hook on):

```console
$ claude-sync init ~/claude-backup --yes
```

## Verify

```console
$ claude-sync status
Destination:      /Users/you/claude-backup (git)
Last backup:      2026-08-14T12:49:04Z
Local changes:    none (in sync)
Session-end hook: installed
Redacted env vars (re-supply after restore): ANTHROPIC_AUTH_TOKEN
```

That's the whole setup. Install a new skill, tweak your settings, end your
Claude Code session — the backup repo gets a new commit by itself.

## Optional: push backups off this machine

If your destination already has a remote when you run `init` (or you
`restore` from a git URL), auto-push is on by default: every backup commit
is pushed immediately. Adding a remote later takes two steps:

1. Give the repo a remote and an upstream once:
   `git -C ~/claude-backup push -u origin main`
2. Run `claude-sync config --auto-push`.

A failed push never fails a backup — the commit stays safe locally and a
warning tells you it will retry on the next backup.

Next: [what backup and restore actually do →](backup-restore.md)
