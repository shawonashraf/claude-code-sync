import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from claude_sync import gitutils
from claude_sync.config import SyncConfig, load_config, save_config
from claude_sync.manifest import marketplace_add_arg
from claude_sync.mirror import MANAGED_DIRS, MANAGED_FILES
from claude_sync.paths import Paths
from claude_sync.redact import REDACTED


class RestoreError(Exception):
    """Restore cannot proceed (bad or missing source)."""


@dataclass
class RestoreResult:
    restored: list[str] = field(default_factory=list)
    failed_plugins: list[tuple[str, str]] = field(default_factory=list)
    redacted_env: list[str] = field(default_factory=list)
    safety_dir: Path | None = None


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "git@", "ssh://", "file://"))


def _backup_files(src: Path):
    for name in MANAGED_FILES:
        if name != "plugins-manifest.json" and (src / name).is_file():
            yield name
    for dirname in MANAGED_DIRS:
        root = src / dirname
        if root.is_dir():
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    yield f.relative_to(src).as_posix()


def run_restore(
    paths: Paths,
    source: str | None,
    to: Path | None = None,
    run=subprocess.run,
    auto_push: bool | None = None,
) -> RestoreResult:
    if source is None:
        cfg = load_config(paths)
        if cfg is None:
            raise RestoreError(
                "no source given and no destination configured; "
                "run: claude-sync restore <path-or-git-url>"
            )
        src = Path(cfg.destination)
    elif _is_url(source):
        src = (to or paths.home / "claude-backup").expanduser()
        try:
            gitutils.clone(source, src)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip().splitlines()[-1] if (exc.stderr or "").strip() else "git clone failed"
            raise RestoreError(f"could not clone {source}: {detail}") from exc
    else:
        src = Path(source).expanduser()
    if not (src / "plugins-manifest.json").is_file():
        raise RestoreError(f"{src} does not look like a claude-sync backup")

    result = RestoreResult()
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    for rel in _backup_files(src):
        local = paths.claude_dir / rel
        if local.is_file():
            if result.safety_dir is None:
                result.safety_dir = paths.safety_dir(timestamp)
            saved = result.safety_dir / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local, saved)
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, local)
        result.restored.append(rel)

    manifest = json.loads((src / "plugins-manifest.json").read_text())
    claude = shutil.which("claude")
    for name, market in manifest.get("marketplaces", {}).items():
        arg = marketplace_add_arg(market.get("source", {}))
        if claude and arg:
            run([claude, "plugin", "marketplace", "add", arg],
                capture_output=True, text=True)
    for plugin in manifest.get("plugins", []):
        if not claude:
            result.failed_plugins.append((plugin["name"], "claude CLI not found"))
            continue
        proc = run([claude, "plugin", "install", plugin["name"]],
                   capture_output=True, text=True)
        if proc.returncode != 0:
            result.failed_plugins.append(
                (plugin["name"], proc.stderr.strip() or "install failed")
            )

    settings_file = paths.settings_file
    if settings_file.is_file():
        env = json.loads(settings_file.read_text()).get("env", {})
        result.redacted_env = sorted(k for k, v in env.items() if v == REDACTED)

    git_mode = gitutils.is_git_repo(src)
    if auto_push is None:
        auto_push = git_mode and gitutils.has_remote(src)
    save_config(paths, SyncConfig(
        destination=str(src), git_mode=git_mode, auto_push=auto_push
    ))
    return result
