import json
import shutil
from pathlib import Path

HOOK_SUBSTRING = "claude-sync backup --quiet"


def hook_command() -> str:
    exe = shutil.which("claude-sync")
    return f"{exe} backup --quiet" if exe else f"uvx {HOOK_SUBSTRING}"


def _load(settings_file: Path) -> dict:
    if not settings_file.exists():
        return {}
    return json.loads(settings_file.read_text())


def _entries(data: dict) -> list:
    return data.setdefault("hooks", {}).setdefault("SessionEnd", [])


def _is_ours(entry: dict) -> bool:
    return any(
        HOOK_SUBSTRING in h.get("command", "")
        for h in entry.get("hooks", [])
    )


def is_hook_installed(settings_file: Path) -> bool:
    return any(_is_ours(e) for e in _load(settings_file).get("hooks", {}).get("SessionEnd", []))


def install_hook(settings_file: Path) -> bool:
    data = _load(settings_file)
    entries = _entries(data)
    if any(_is_ours(e) for e in entries):
        return False
    entries.append({"hooks": [{"type": "command", "command": hook_command()}]})
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
