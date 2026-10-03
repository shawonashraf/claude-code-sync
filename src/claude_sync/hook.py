import json
import re
import shutil
from pathlib import Path

HOOK_SUBSTRING = "claude-sync backup --quiet"
# on Windows shutil.which resolves to claude-sync.EXE, so match the marker loosely
_HOOK_RE = re.compile(r"claude-sync(\.exe)?\"? backup --quiet", re.IGNORECASE)


def is_hook_command(command: str) -> bool:
    return bool(_HOOK_RE.search(command))


def hook_command() -> str:
    exe = shutil.which("claude-sync")
    # PyPI package is claude-code-sync; --from keeps the marker substring intact
    if exe:
        # Claude Code runs hooks through bash, which eats backslashes
        exe = Path(exe).as_posix()
        if " " in exe:
            exe = f'"{exe}"'
        return f"{exe} backup --quiet"
    return f"uvx --from claude-code-sync {HOOK_SUBSTRING}"


def _load(settings_file: Path) -> dict:
    if not settings_file.exists():
        return {}
    return json.loads(settings_file.read_text(encoding="utf-8"))


def _entries(data: dict) -> list:
    return data.setdefault("hooks", {}).setdefault("SessionEnd", [])


def _is_ours(entry: dict) -> bool:
    return any(
        is_hook_command(h.get("command", ""))
        for h in entry.get("hooks", [])
    )


def is_hook_installed(settings_file: Path) -> bool:
    return any(_is_ours(e) for e in _load(settings_file).get("hooks", {}).get("SessionEnd", []))


def install_hook(settings_file: Path) -> bool:
    data = _load(settings_file)
    entries = _entries(data)
    if any(_is_ours(e) for e in entries):
        return False
    entries.append({"hooks": [{
        "type": "command",
        "command": hook_command(),
        # async + timeout: Claude Code cancels synchronous SessionEnd hooks
        # that outlive app shutdown; a backup can take seconds when it pushes
        "async": True,
        "timeout": 60,
    }]})
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(data, indent=2) + "\n")
    return True


def uninstall_hook(settings_file: Path) -> bool:
    data = _load(settings_file)
    entries = _entries(data)
    kept = [e for e in entries if not _is_ours(e)]
    if len(kept) == len(entries):
        return False
    data["hooks"]["SessionEnd"] = kept
    settings_file.write_text(json.dumps(data, indent=2) + "\n")
    return True
