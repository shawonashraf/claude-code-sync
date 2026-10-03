from dataclasses import dataclass, field
from pathlib import Path

from claude_sync.variant import managed_dirs, managed_files


@dataclass
class Changes:
    writes: list[str] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.writes and not self.deletes


def _existing_managed(dest: Path, variant: str | None) -> set[str]:
    found: set[str] = set()
    for dirname in managed_dirs(variant):
        root = dest / dirname
        if root.is_dir():
            for f in root.rglob("*"):
                if f.is_file():
                    found.add(f.relative_to(dest).as_posix())
    for name in managed_files(variant):
        if (dest / name).is_file():
            found.add(name)
    return found


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)


def _set_executable(path: Path, executable: bool) -> None:
    mode = path.stat().st_mode & 0o777
    # mirror each read bit into its exec bit so umask-style perms are kept
    new = mode | ((mode & 0o444) >> 2) if executable else mode & ~0o111
    if new != mode:
        path.chmod(new)


def diff_dest(
    files: dict[str, bytes], dest: Path, executables: frozenset[str] = frozenset(),
    variant: str | None = None,
) -> Changes:
    changes = Changes()
    for rel, content in sorted(files.items()):
        target = dest / rel
        if not target.is_file() or target.stat().st_size != len(content) \
                or target.read_bytes() != content \
                or _is_executable(target) != (rel in executables):
            changes.writes.append(rel)
    changes.deletes = sorted(_existing_managed(dest, variant) - set(files))
    return changes


def apply_changes(
    files: dict[str, bytes], dest: Path, changes: Changes,
    executables: frozenset[str] = frozenset(),
) -> None:
    for rel in changes.writes:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[rel])
        # hooks are run directly by Claude Code, so the exec bit must survive
        # the round trip (git tracks it; shutil.copy2 restores it)
        _set_executable(target, rel in executables)
    for rel in changes.deletes:
        target = dest / rel
        target.unlink(missing_ok=True)
        parent = target.parent
        while parent != dest and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
