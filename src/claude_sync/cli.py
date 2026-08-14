import argparse
import json
import os
import sys
from pathlib import Path

from claude_sync import hook
from claude_sync.backup import run_backup
from claude_sync.lock import AlreadyRunning
from claude_sync.paths import Paths
from claude_sync.restore import RestoreError, run_restore
from claude_sync.statuscmd import gather_status, render_status
from claude_sync.wizard import run_init


def build_paths() -> Paths:
    home = os.environ.get("CLAUDE_SYNC_HOME")
    return Paths(home=Path(home) if home else Path.home())


class InteractivePrompts:
    """rich + questionary implementation of wizard.Prompts."""

    def __init__(self):
        from rich.console import Console
        self.console = Console()

    def ask_destination(self, default: str) -> str:
        import questionary
        return questionary.path(
            "Where should your Claude settings be backed up?", default=default
        ).ask() or default

    def confirm(self, message: str, default: bool = True) -> bool:
        import questionary
        answer = questionary.confirm(message, default=default).ask()
        return default if answer is None else answer

    def info(self, message: str) -> None:
        from rich.panel import Panel
        self.console.print(Panel.fit(message))


def interactive_resolver() -> str | None:
    import questionary
    choice = questionary.select(
        "Your backup has two conflicting versions: this machine's and the one "
        "in the repo. Keeping one loses the other from the working copy — the "
        "losing version stays in git history.",
        choices=[
            questionary.Choice("Keep this machine's version", value="local"),
            questionary.Choice("Keep the repo's version", value="repo"),
            questionary.Choice("Cancel", value=None),
        ],
    ).ask()
    return choice


def _cmd_backup(paths: Paths, args) -> int:
    resolver = None if args.quiet else interactive_resolver
    try:
        result = run_backup(paths, resolver=resolver)
    except AlreadyRunning:
        return 0  # another run is already syncing; nothing to do
    if result.status == "not-configured":
        print("claude-sync is not configured. Run: claude-sync init",
              file=sys.stderr)
        return 1
    if result.status == "conflict-pending":
        print("claude-sync: backup skipped — destination has conflicting "
              "versions. Run: claude-sync resolve", file=sys.stderr)
        return 1
    if result.status == "kept-repo":
        print("Kept the repo's version. Run `claude-sync restore` to adopt "
              "it on this machine.")
        return 0
    if not args.quiet:
        if result.status == "ok":
            print(f"Backed up to {gather_status(paths).destination}"
                  + (" (committed)" if result.committed else ""))
        if args.show_redactions and result.redacted:
            print("Redacted env vars: " + ", ".join(result.redacted))
    return 0


def _cmd_restore(paths: Paths, args) -> int:
    try:
        result = run_restore(paths, args.source,
                             to=Path(args.to) if args.to else None)
    except RestoreError as exc:
        print(f"claude-sync: {exc}", file=sys.stderr)
        return 1
    print(f"Restored {len(result.restored)} files.")
    if result.safety_dir:
        print(f"Previous local files saved to {result.safety_dir}")
    for name, err in result.failed_plugins:
        print(f"FAILED plugin {name}: {err}\n  retry: claude plugin install {name}")
    if result.redacted_env:
        print("Re-supply these env vars in ~/.claude/settings.json: "
              + ", ".join(result.redacted_env))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-sync",
        description="Back up and restore your Claude Code configuration.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="set up backups on this machine")
    p_init.add_argument("destination", nargs="?")
    p_init.add_argument("--yes", action="store_true",
                        help="accept all defaults, no prompts")

    p_backup = sub.add_parser("backup", help="run one backup pass")
    p_backup.add_argument("--quiet", action="store_true")
    p_backup.add_argument("--show-redactions", action="store_true")

    p_restore = sub.add_parser("restore", help="restore settings from a backup")
    p_restore.add_argument("source", nargs="?")
    p_restore.add_argument("--to", help="clone location for git URL sources")

    sub.add_parser("status", help="show sync status")
    sub.add_parser("resolve", help="resolve a pending backup conflict")

    p_hook = sub.add_parser("hook", help="manage the session-end hook")
    p_hook.add_argument("action", choices=["install", "uninstall"])

    args = parser.parse_args(argv)
    paths = build_paths()

    try:
        if args.command == "init":
            prompts = InteractivePrompts() if not args.yes else _SilentPrompts()
            return run_init(paths, args.destination, args.yes, prompts)
        if args.command == "backup":
            return _cmd_backup(paths, args)
        if args.command == "restore":
            return _cmd_restore(paths, args)
        if args.command == "status":
            print(render_status(gather_status(paths)))
            return 0
        if args.command == "resolve":
            args.quiet = False
            args.show_redactions = False
            return _cmd_backup(paths, args)
        if args.command == "hook":
            if args.action == "install":
                hook.install_hook(paths.settings_file)
            else:
                hook.uninstall_hook(paths.settings_file)
            try:
                run_backup(paths)  # destination must reflect the settings change
            except AlreadyRunning:
                pass  # another run is syncing; it will pick up the hook change
            return 0
        return 2
    except json.JSONDecodeError as exc:
        print(f"claude-sync: invalid JSON in a config file: {exc}",
              file=sys.stderr)
        return 1


class _SilentPrompts:
    def ask_destination(self, default: str) -> str:
        return default

    def confirm(self, message: str, default: bool = True) -> bool:
        return default

    def info(self, message: str) -> None:
        print(message)


if __name__ == "__main__":
    raise SystemExit(main())
