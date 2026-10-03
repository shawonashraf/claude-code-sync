import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_manifest(claude_dir: Path, cache_symlinks: list[str] | None = None) -> dict:
    plugins_dir = claude_dir / "plugins"
    installed = _read_json(plugins_dir / "installed_plugins.json")
    known = _read_json(plugins_dir / "known_marketplaces.json")

    marketplaces = {
        name: {"source": data["source"]}
        for name, data in known.items()
        if isinstance(data, dict) and "source" in data
    }
    plugins = []
    for name, entries in sorted(installed.get("plugins", {}).items()):
        entry = entries[0] if entries else {}
        plugins.append({
            "name": name,
            "version": entry.get("version"),
            "scope": entry.get("scope", "user"),
        })
    return {
        "schema": 1,
        "marketplaces": marketplaces,
        "plugins": plugins,
        "cache_symlinks": sorted(cache_symlinks or []),
    }


def marketplace_add_arg(source: dict) -> str | None:
    for field in ("repo", "url", "path"):
        if field in source:
            return source[field]
    return None
