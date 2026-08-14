import json
from dataclasses import dataclass, field
from pathlib import Path

from claude_sync.manifest import build_manifest
from claude_sync.redact import redact_settings

MIRROR_DIRS = ("skills", "hooks", "agents")
SINGLE_FILES = ("keybindings.json", "CLAUDE.md")


@dataclass
class SyncSet:
    files: dict[str, bytes] = field(default_factory=dict)
    redacted_env: list[str] = field(default_factory=list)


def _is_cache_symlink(path: Path, claude_dir: Path) -> bool:
    if not path.is_symlink():
        return False
    cache = (claude_dir / "plugins" / "cache").resolve()
    return path.resolve().is_relative_to(cache)


def build_sync_set(claude_dir: Path) -> SyncSet:
    ss = SyncSet()
    cache_symlinks: list[str] = []

    for dirname in MIRROR_DIRS:
        root = claude_dir / dirname
        if not root.is_dir():
            continue
        for entry in sorted(root.rglob("*")):
            rel = entry.relative_to(claude_dir).as_posix()
            if _is_cache_symlink(entry, claude_dir):
                cache_symlinks.append(rel)
                continue
            if any(_is_cache_symlink(p, claude_dir) for p in entry.parents):
                continue
            if entry.is_file():
                ss.files[rel] = entry.read_bytes()

    for name in SINGLE_FILES:
        f = claude_dir / name
        if f.is_file():
            ss.files[name] = f.read_bytes()

    settings_file = claude_dir / "settings.json"
    if settings_file.is_file():
        redacted, names = redact_settings(json.loads(settings_file.read_text()))
        ss.files["settings.json"] = (json.dumps(redacted, indent=2) + "\n").encode()
        ss.redacted_env = names

    manifest = build_manifest(claude_dir, cache_symlinks=cache_symlinks)
    ss.files["plugins-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return ss
