import json
from dataclasses import dataclass, field
from pathlib import Path

from claude_sync.manifest import build_manifest
from claude_sync.redact import redact_settings
from claude_sync.variant import repo_rel

MIRROR_DIRS = ("skills", "hooks", "agents")
SINGLE_FILES = ("keybindings.json", "CLAUDE.md")


@dataclass
class SyncSet:
    files: dict[str, bytes] = field(default_factory=dict)
    executables: set[str] = field(default_factory=set)
    redacted_env: list[str] = field(default_factory=list)


def _is_cache_symlink(path: Path, claude_dir: Path) -> bool:
    if not path.is_symlink():
        return False
    cache = (claude_dir / "plugins" / "cache").resolve()
    return path.resolve().is_relative_to(cache)


def build_sync_set(claude_dir: Path, variant: str | None = None) -> SyncSet:
    ss = SyncSet()
    cache_symlinks: list[str] = []

    for dirname in MIRROR_DIRS:
        root = claude_dir / dirname
        if not root.is_dir():
            continue
        for entry in sorted(root.rglob("*")):
            local = entry.relative_to(claude_dir).as_posix()
            rel = repo_rel(local, variant)
            # dot-prefixed files/dirs inside mirrors are runtime state
            # (.state.json, .sound.pid), not configuration — never synced
            if any(part.startswith(".") for part in entry.relative_to(root).parts):
                continue
            if _is_cache_symlink(entry, claude_dir):
                cache_symlinks.append(local)
                continue
            if any(_is_cache_symlink(p, claude_dir) for p in entry.parents):
                continue
            if entry.is_file():
                ss.files[rel] = entry.read_bytes()
                if entry.stat().st_mode & 0o111:
                    ss.executables.add(rel)

    for name in SINGLE_FILES:
        f = claude_dir / name
        if f.is_file():
            ss.files[name] = f.read_bytes()

    settings_file = claude_dir / "settings.json"
    if settings_file.is_file():
        redacted, names = redact_settings(
            json.loads(settings_file.read_text(encoding="utf-8")))
        ss.files[repo_rel("settings.json", variant)] = (json.dumps(redacted, indent=2) + "\n").encode()
        ss.redacted_env = names

    manifest = build_manifest(claude_dir, cache_symlinks=cache_symlinks)
    ss.files["plugins-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return ss
