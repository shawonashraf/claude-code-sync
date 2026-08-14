from dataclasses import dataclass, field
from pathlib import Path

MANAGED_DIRS = ("skills", "hooks", "agents")
MANAGED_FILES = ("settings.json", "keybindings.json", "CLAUDE.md", "plugins-manifest.json")


@dataclass
class Changes:
    writes: list[str] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.writes and not self.deletes


def _existing_managed(dest: Path) -> set[str]:
    found: set[str] = set()
    for dirname in MANAGED_DIRS:
        root = dest / dirname
        if root.is_dir():
            for f in root.rglob("*"):
                if f.is_file():
                    found.add(f.relative_to(dest).as_posix())
    for name in MANAGED_FILES:
        if (dest / name).is_file():
            found.add(name)
    return found


def diff_dest(files: dict[str, bytes], dest: Path) -> Changes:
    changes = Changes()
    for rel, content in sorted(files.items()):
        target = dest / rel
        if not target.is_file() or target.stat().st_size != len(content) \
                or target.read_bytes() != content:
            changes.writes.append(rel)
    changes.deletes = sorted(_existing_managed(dest) - set(files))
    return changes


def apply_changes(files: dict[str, bytes], dest: Path, changes: Changes) -> None:
    for rel in changes.writes:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[rel])
    for rel in changes.deletes:
        target = dest / rel
        target.unlink(missing_ok=True)
        parent = target.parent
        while parent != dest and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
