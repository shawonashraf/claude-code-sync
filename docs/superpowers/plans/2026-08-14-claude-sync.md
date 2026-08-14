# claude-sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI that backs up Claude Code configuration (skills, hooks, agents, plugin manifest, redacted settings) to a user-chosen directory or git repo, and restores it on a new machine with one command.

**Architecture:** Thin Python CLI with a declarative sync set. Pure modules (redaction, manifest, mirror diff, git helpers) composed by two orchestrators (`backup`, `restore`). Interactive I/O (init wizard, conflict prompts) is isolated behind small callables so every flow is testable without a TTY.

**Tech Stack:** Python 3.13, `uv`, `hatchling`; runtime deps `rich` + `questionary`; tests with `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-14-claude-sync-design.md`

## Global Constraints

- Python `>=3.13`; runtime dependencies exactly `rich` and `questionary`; dev dependency `pytest`.
- Only these paths are ever read from `~/.claude`: `skills/`, `hooks/`, `agents/`, `settings.json`, `keybindings.json`, `CLAUDE.md`, `plugins/installed_plugins.json`, `plugins/known_marketplaces.json`. Nothing else — never history, sessions, projects.
- Tool config lives at `~/.claude-sync.json`, lock at `~/.claude-sync.lock`, safety copies at `~/.claude-sync-backup-<timestamp>/` — all outside `~/.claude`.
- The redaction placeholder is the literal string `<redacted-by-claude-sync>`.
- The tool never runs `git pull`, `git fetch`, `git merge` (except the two explicit resolution strategies), or any force push.
- All code under `src/claude_sync/`; tests under `tests/`; every filesystem test uses `tmp_path`, never the real `$HOME`.
- Commit after every green task, staging files by name.

## File Structure

```
pyproject.toml               # deps, console script, pytest config
src/claude_sync/__init__.py  # __version__
src/claude_sync/paths.py     # Paths dataclass: all well-known locations
src/claude_sync/config.py    # SyncConfig load/save (~/.claude-sync.json)
src/claude_sync/redact.py    # settings.json secret redaction
src/claude_sync/manifest.py  # plugins-manifest.json generation
src/claude_sync/syncset.py   # build in-memory sync set from ~/.claude
src/claude_sync/mirror.py    # diff + apply against destination
src/claude_sync/lock.py      # lockfile guard
src/claude_sync/gitutils.py  # git detect/commit/divergence/resolution/clone
src/claude_sync/backup.py    # backup orchestration
src/claude_sync/hook.py      # SessionEnd hook install/uninstall
src/claude_sync/restore.py   # restore orchestration
src/claude_sync/statuscmd.py # status gathering + rendering
src/claude_sync/wizard.py    # init flow behind a Prompts protocol
src/claude_sync/cli.py       # argparse dispatch, interactive prompts impl
tests/conftest.py            # fixture ~/.claude tree + git repo helpers
tests/test_<module>.py       # one test file per module
tests/test_end_to_end.py     # backup→restore smoke test
```

---

### Task 1: Project scaffold, `paths.py`, `config.py`

**Files:**
- Modify: `pyproject.toml`
- Delete: `main.py`
- Create: `src/claude_sync/__init__.py`, `src/claude_sync/paths.py`, `src/claude_sync/config.py`, `tests/__init__.py` (empty), `tests/test_config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Paths(home: Path)` with properties `claude_dir`, `settings_file`, `plugins_dir`, `config_file`, `lock_file` and method `safety_dir(timestamp: str) -> Path`. `SyncConfig(destination: str, git_mode: bool = False, auto_push: bool = False, conflict_pending: bool = False, last_backup: str | None = None)`. `load_config(paths) -> SyncConfig | None`, `save_config(paths, config) -> None`.

- [ ] **Step 1: Rewrite `pyproject.toml` and remove the scaffold `main.py`**

```toml
[project]
name = "claude-sync"
version = "0.1.0"
description = "Back up and restore your Claude Code configuration (skills, plugins, hooks, settings)"
readme = "README.md"
requires-python = ">=3.13"
dependencies = ["rich>=13", "questionary>=2"]

[project.scripts]
claude-sync = "claude_sync.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/claude_sync"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Run: `rm main.py && mkdir -p src/claude_sync tests`

`src/claude_sync/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 2: Write the failing tests**

`tests/test_config.py`:

```python
from pathlib import Path

from claude_sync.config import SyncConfig, load_config, save_config
from claude_sync.paths import Paths


def test_paths_layout(tmp_path):
    p = Paths(home=tmp_path)
    assert p.claude_dir == tmp_path / ".claude"
    assert p.settings_file == tmp_path / ".claude" / "settings.json"
    assert p.plugins_dir == tmp_path / ".claude" / "plugins"
    assert p.config_file == tmp_path / ".claude-sync.json"
    assert p.lock_file == tmp_path / ".claude-sync.lock"
    assert p.safety_dir("20260814-051500") == tmp_path / ".claude-sync-backup-20260814-051500"


def test_load_config_missing_returns_none(tmp_path):
    assert load_config(Paths(home=tmp_path)) is None


def test_config_roundtrip(tmp_path):
    p = Paths(home=tmp_path)
    cfg = SyncConfig(destination="/backups/claude", git_mode=True, auto_push=True)
    save_config(p, cfg)
    loaded = load_config(p)
    assert loaded == cfg
    assert loaded.conflict_pending is False
    assert loaded.last_backup is None


def test_load_config_ignores_unknown_keys(tmp_path):
    p = Paths(home=tmp_path)
    p.config_file.write_text('{"destination": "/d", "future_field": 1}')
    assert load_config(p) == SyncConfig(destination="/d")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_sync.config'` (uv will first sync deps; that is fine).

- [ ] **Step 4: Implement**

`src/claude_sync/paths.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def claude_dir(self) -> Path:
        return self.home / ".claude"

    @property
    def settings_file(self) -> Path:
        return self.claude_dir / "settings.json"

    @property
    def plugins_dir(self) -> Path:
        return self.claude_dir / "plugins"

    @property
    def config_file(self) -> Path:
        return self.home / ".claude-sync.json"

    @property
    def lock_file(self) -> Path:
        return self.home / ".claude-sync.lock"

    def safety_dir(self, timestamp: str) -> Path:
        return self.home / f".claude-sync-backup-{timestamp}"
```

`src/claude_sync/config.py`:

```python
import dataclasses
import json
from dataclasses import dataclass

from claude_sync.paths import Paths


@dataclass
class SyncConfig:
    destination: str
    git_mode: bool = False
    auto_push: bool = False
    conflict_pending: bool = False
    last_backup: str | None = None


def load_config(paths: Paths) -> SyncConfig | None:
    if not paths.config_file.exists():
        return None
    data = json.loads(paths.config_file.read_text())
    known = {f.name for f in dataclasses.fields(SyncConfig)}
    return SyncConfig(**{k: v for k, v in data.items() if k in known})


def save_config(paths: Paths, config: SyncConfig) -> None:
    paths.config_file.write_text(
        json.dumps(dataclasses.asdict(config), indent=2) + "\n"
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/claude_sync/__init__.py src/claude_sync/paths.py src/claude_sync/config.py tests/__init__.py tests/test_config.py uv.lock
git rm main.py
git commit -m "feat: project scaffold with Paths and SyncConfig"
```

---

### Task 2: Redaction (`redact.py`)

**Files:**
- Create: `src/claude_sync/redact.py`
- Test: `tests/test_redact.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `REDACTED: str` (the placeholder literal) and `redact_settings(settings: dict) -> tuple[dict, list[str]]` returning a deep-copied redacted dict plus the sorted list of redacted env var names. Input dict is never mutated.

- [ ] **Step 1: Write the failing tests**

`tests/test_redact.py`:

```python
from claude_sync.redact import REDACTED, redact_settings


def test_redacts_sensitive_env_names():
    settings = {"env": {
        "MY_API_KEY": "abc123",
        "GITHUB_TOKEN": "x",
        "DB_PASSWORD": "y",
        "AWS_SECRET_ACCESS_KEY": "z",
        "SOME_CREDENTIAL": "c",
    }}
    redacted, names = redact_settings(settings)
    assert all(v == REDACTED for v in redacted["env"].values())
    assert names == sorted(settings["env"])


def test_redacts_secret_shaped_values_despite_benign_name():
    settings = {"env": {
        "HELPER": "sk-ant-abcdefghij1234567890",
        "OTHER": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
        "ENTROPIC": "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6",
    }}
    redacted, names = redact_settings(settings)
    assert all(v == REDACTED for v in redacted["env"].values())
    assert names == ["ENTROPIC", "HELPER", "OTHER"]


def test_keeps_benign_env_and_all_other_keys():
    settings = {
        "env": {"EDITOR": "vim", "CLAUDE_CODE_ENABLE_TELEMETRY": "0"},
        "model": "opus",
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {"SessionEnd": []},
    }
    redacted, names = redact_settings(settings)
    assert redacted == settings
    assert names == []


def test_input_not_mutated():
    settings = {"env": {"API_KEY": "secret"}}
    redact_settings(settings)
    assert settings["env"]["API_KEY"] == "secret"


def test_no_env_key_is_fine():
    assert redact_settings({"model": "opus"}) == ({"model": "opus"}, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_redact.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/redact.py`:

```python
import copy
import re

REDACTED = "<redacted-by-claude-sync>"

_SENSITIVE_NAME = re.compile(r"key|token|secret|password|credential", re.IGNORECASE)
_SECRET_PREFIX = re.compile(r"^(sk-|ghp_|gho_|github_pat_|glpat-|xox[a-z]-|AKIA)")
_BASE64ISH = re.compile(r"^[A-Za-z0-9+/=_\-]{32,}$")


def _looks_like_secret(value: str) -> bool:
    if _SECRET_PREFIX.match(value):
        return True
    return bool(
        _BASE64ISH.match(value)
        and any(c.isdigit() for c in value)
        and any(c.isalpha() for c in value)
    )


def redact_settings(settings: dict) -> tuple[dict, list[str]]:
    result = copy.deepcopy(settings)
    names: list[str] = []
    env = result.get("env")
    if isinstance(env, dict):
        for name, value in env.items():
            if _SENSITIVE_NAME.search(name) or (
                isinstance(value, str) and _looks_like_secret(value)
            ):
                env[name] = REDACTED
                names.append(name)
    return result, sorted(names)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_redact.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_sync/redact.py tests/test_redact.py
git commit -m "feat: settings.json secret redaction"
```

---

### Task 3: Plugin manifest (`manifest.py`)

**Files:**
- Create: `src/claude_sync/manifest.py`, `tests/conftest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: `Paths` (Task 1) in the conftest fixture only.
- Produces: `build_manifest(claude_dir: Path, cache_symlinks: list[str] | None = None) -> dict` with shape `{"schema": 1, "marketplaces": {name: {"source": {...}}}, "plugins": [{"name": "x@mkt", "version": str|None, "scope": str}], "cache_symlinks": [...]}`. Also `marketplace_add_arg(source: dict) -> str | None` (used by restore, Task 10). Conftest produces the shared fixture `fake_claude(tmp_path) -> Paths`.

- [ ] **Step 1: Write the shared fixture**

`tests/conftest.py`:

```python
import json

import pytest

from claude_sync.paths import Paths

INSTALLED_PLUGINS = {
    "version": 2,
    "plugins": {
        "swift-lsp@claude-plugins-official": [{
            "scope": "user",
            "installPath": "/machine/specific/path",
            "version": "1.0.0",
            "installedAt": "2026-04-07T22:51:17.824Z",
        }],
        "superpowers@claude-plugins-official": [{
            "scope": "user",
            "installPath": "/machine/specific/other",
            "version": "6.3.0",
            "installedAt": "2026-04-07T23:23:51.602Z",
        }],
    },
}

KNOWN_MARKETPLACES = {
    "claude-plugins-official": {
        "source": {"source": "github", "repo": "anthropics/claude-plugins-official"},
        "installLocation": "/machine/specific/marketplace",
        "lastUpdated": "2026-08-14T03:22:52.974Z",
    },
}

SETTINGS = {
    "env": {"MY_API_KEY": "supersecret", "EDITOR": "vim"},
    "model": "opus",
    "permissions": {"allow": ["Bash(ls:*)"]},
    "enabledPlugins": {"superpowers@claude-plugins-official": True},
}


@pytest.fixture
def fake_claude(tmp_path) -> Paths:
    """A realistic ~/.claude tree under tmp_path/home."""
    home = tmp_path / "home"
    paths = Paths(home=home)
    cd = paths.claude_dir
    (cd / "skills" / "my-skill").mkdir(parents=True)
    (cd / "skills" / "my-skill" / "SKILL.md").write_text("# My Skill\n")
    (cd / "hooks" / "peon").mkdir(parents=True)
    (cd / "hooks" / "peon" / "run.sh").write_text("#!/bin/sh\necho hi\n")
    (cd / "agents").mkdir()
    (cd / "agents" / "helper.md").write_text("agent def\n")
    (cd / "CLAUDE.md").write_text("global instructions\n")
    (cd / "keybindings.json").write_text('{"submit": "enter"}\n')
    paths.settings_file.write_text(json.dumps(SETTINGS))
    paths.plugins_dir.mkdir()
    (paths.plugins_dir / "installed_plugins.json").write_text(json.dumps(INSTALLED_PLUGINS))
    (paths.plugins_dir / "known_marketplaces.json").write_text(json.dumps(KNOWN_MARKETPLACES))
    # Noise that must never be synced:
    (cd / "history.jsonl").write_text('{"secret": "chat"}\n')
    (cd / "projects").mkdir()
    (cd / "projects" / "p.json").write_text("{}")
    return paths
```

- [ ] **Step 2: Write the failing tests**

`tests/test_manifest.py`:

```python
import json

from claude_sync.manifest import build_manifest, marketplace_add_arg


def test_manifest_distills_plugins_and_marketplaces(fake_claude):
    m = build_manifest(fake_claude.claude_dir)
    assert m["schema"] == 1
    assert m["marketplaces"] == {
        "claude-plugins-official": {
            "source": {"source": "github", "repo": "anthropics/claude-plugins-official"}
        }
    }
    names = {p["name"] for p in m["plugins"]}
    assert names == {"swift-lsp@claude-plugins-official", "superpowers@claude-plugins-official"}
    swift = next(p for p in m["plugins"] if p["name"].startswith("swift"))
    assert swift == {"name": "swift-lsp@claude-plugins-official", "version": "1.0.0", "scope": "user"}


def test_manifest_drops_machine_specific_fields(fake_claude):
    text = json.dumps(build_manifest(fake_claude.claude_dir))
    assert "installPath" not in text
    assert "installLocation" not in text
    assert "/machine/specific" not in text


def test_manifest_records_cache_symlinks(fake_claude):
    m = build_manifest(fake_claude.claude_dir, cache_symlinks=["skills/linked-skill"])
    assert m["cache_symlinks"] == ["skills/linked-skill"]


def test_manifest_empty_when_no_plugin_files(tmp_path):
    m = build_manifest(tmp_path)
    assert m["plugins"] == [] and m["marketplaces"] == {}


def test_marketplace_add_arg_variants():
    assert marketplace_add_arg({"source": "github", "repo": "a/b"}) == "a/b"
    assert marketplace_add_arg({"source": "url", "url": "https://x/mp.git"}) == "https://x/mp.git"
    assert marketplace_add_arg({"source": "directory", "path": "/p"}) == "/p"
    assert marketplace_add_arg({"source": "mystery"}) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_sync.manifest'`

- [ ] **Step 4: Implement**

`src/claude_sync/manifest.py`:

```python
import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add src/claude_sync/manifest.py tests/conftest.py tests/test_manifest.py
git commit -m "feat: plugin manifest generation from installed_plugins/known_marketplaces"
```

---

### Task 4: Sync set builder (`syncset.py`)

**Files:**
- Create: `src/claude_sync/syncset.py`
- Test: `tests/test_syncset.py`

**Interfaces:**
- Consumes: `redact_settings`, `REDACTED` (Task 2); `build_manifest` (Task 3).
- Produces: `SyncSet(files: dict[str, bytes], redacted_env: list[str])` and `build_sync_set(claude_dir: Path) -> SyncSet`. Keys of `files` are destination-relative POSIX paths (e.g. `skills/my-skill/SKILL.md`, `settings.json`, `plugins-manifest.json`). Constants `MIRROR_DIRS = ("skills", "hooks", "agents")` and `SINGLE_FILES = ("keybindings.json", "CLAUDE.md")`.

- [ ] **Step 1: Write the failing tests**

`tests/test_syncset.py`:

```python
import json

from claude_sync.redact import REDACTED
from claude_sync.syncset import build_sync_set


def test_sync_set_contains_exactly_the_managed_paths(fake_claude):
    ss = build_sync_set(fake_claude.claude_dir)
    assert set(ss.files) == {
        "skills/my-skill/SKILL.md",
        "hooks/peon/run.sh",
        "agents/helper.md",
        "CLAUDE.md",
        "keybindings.json",
        "settings.json",
        "plugins-manifest.json",
    }


def test_sync_set_never_includes_history_or_projects(fake_claude):
    ss = build_sync_set(fake_claude.claude_dir)
    assert not any("history" in k or "projects" in k for k in ss.files)


def test_settings_are_redacted_in_sync_set(fake_claude):
    ss = build_sync_set(fake_claude.claude_dir)
    settings = json.loads(ss.files["settings.json"])
    assert settings["env"]["MY_API_KEY"] == REDACTED
    assert settings["env"]["EDITOR"] == "vim"
    assert ss.redacted_env == ["MY_API_KEY"]


def test_cache_symlinks_skipped_and_recorded(fake_claude):
    cache_target = fake_claude.plugins_dir / "cache" / "mp" / "plug" / "skill-dir"
    cache_target.mkdir(parents=True)
    link = fake_claude.claude_dir / "skills" / "linked-skill"
    link.symlink_to(cache_target)
    ss = build_sync_set(fake_claude.claude_dir)
    assert not any(k.startswith("skills/linked-skill") for k in ss.files)
    manifest = json.loads(ss.files["plugins-manifest.json"])
    assert manifest["cache_symlinks"] == ["skills/linked-skill"]


def test_missing_optional_pieces_are_fine(tmp_path):
    (tmp_path / "skills").mkdir()
    ss = build_sync_set(tmp_path)
    assert "plugins-manifest.json" in ss.files
    assert "keybindings.json" not in ss.files
    assert "settings.json" not in ss.files
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_syncset.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/syncset.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_syncset.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_sync/syncset.py tests/test_syncset.py
git commit -m "feat: in-memory sync set builder"
```

---

### Task 5: Mirror engine (`mirror.py`)

**Files:**
- Create: `src/claude_sync/mirror.py`
- Test: `tests/test_mirror.py`

**Interfaces:**
- Consumes: sync-set `files` dict shape (Task 4).
- Produces: `Changes(writes: list[str], deletes: list[str])` with property `empty: bool`; `diff_dest(files: dict[str, bytes], dest: Path) -> Changes`; `apply_changes(files: dict[str, bytes], dest: Path, changes: Changes) -> None`. Constants `MANAGED_DIRS = ("skills", "hooks", "agents")`, `MANAGED_FILES = ("settings.json", "keybindings.json", "CLAUDE.md", "plugins-manifest.json")`. Only managed paths are ever deleted; `.git` and `claude-sync.meta.json` are untouchable.

- [ ] **Step 1: Write the failing tests**

`tests/test_mirror.py`:

```python
from claude_sync.mirror import Changes, apply_changes, diff_dest

FILES = {
    "skills/a/SKILL.md": b"alpha",
    "settings.json": b"{}",
}


def test_fresh_dest_writes_everything(tmp_path):
    changes = diff_dest(FILES, tmp_path)
    assert sorted(changes.writes) == ["settings.json", "skills/a/SKILL.md"]
    assert changes.deletes == []
    assert not changes.empty


def test_apply_then_rediff_is_empty(tmp_path):
    changes = diff_dest(FILES, tmp_path)
    apply_changes(FILES, tmp_path, changes)
    assert (tmp_path / "skills" / "a" / "SKILL.md").read_bytes() == b"alpha"
    assert diff_dest(FILES, tmp_path).empty


def test_changed_content_rewrites_only_that_file(tmp_path):
    apply_changes(FILES, tmp_path, diff_dest(FILES, tmp_path))
    updated = dict(FILES, **{"skills/a/SKILL.md": b"alpha v2"})
    changes = diff_dest(updated, tmp_path)
    assert changes.writes == ["skills/a/SKILL.md"] and changes.deletes == []


def test_stale_managed_files_are_deleted(tmp_path):
    apply_changes(FILES, tmp_path, diff_dest(FILES, tmp_path))
    shrunk = {"settings.json": b"{}"}
    changes = diff_dest(shrunk, tmp_path)
    assert changes.deletes == ["skills/a/SKILL.md"]
    apply_changes(shrunk, tmp_path, changes)
    assert not (tmp_path / "skills" / "a").exists()  # empty dirs pruned


def test_git_and_meta_never_deleted(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref")
    (tmp_path / "claude-sync.meta.json").write_text("{}")
    (tmp_path / "unmanaged-note.txt").write_text("keep me")
    changes = diff_dest(FILES, tmp_path)
    assert changes.deletes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mirror.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/mirror.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mirror.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_sync/mirror.py tests/test_mirror.py
git commit -m "feat: destination mirror diff and apply"
```

---

### Task 6: Lockfile (`lock.py`)

**Files:**
- Create: `src/claude_sync/lock.py`
- Test: `tests/test_lock.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AlreadyRunning(Exception)` and context manager `sync_lock(lock_file: Path)`. Second concurrent acquisition raises `AlreadyRunning`; a lock left by a dead process is stolen.

- [ ] **Step 1: Write the failing tests**

`tests/test_lock.py`:

```python
import pytest

from claude_sync.lock import AlreadyRunning, sync_lock


def test_lock_acquire_release(tmp_path):
    lock = tmp_path / "l.lock"
    with sync_lock(lock):
        assert lock.exists()
    assert not lock.exists()


def test_second_acquire_raises(tmp_path):
    lock = tmp_path / "l.lock"
    with sync_lock(lock):
        with pytest.raises(AlreadyRunning):
            with sync_lock(lock):
                pass


def test_stale_lock_from_dead_pid_is_stolen(tmp_path):
    lock = tmp_path / "l.lock"
    lock.write_text("99999999")  # no such pid
    with sync_lock(lock):
        assert lock.exists()
    assert not lock.exists()


def test_lock_released_on_exception(tmp_path):
    lock = tmp_path / "l.lock"
    with pytest.raises(ValueError):
        with sync_lock(lock):
            raise ValueError("boom")
    assert not lock.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_lock.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/lock.py`:

```python
import contextlib
import os
from pathlib import Path


class AlreadyRunning(Exception):
    """Another claude-sync run holds the lock."""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


@contextlib.contextmanager
def sync_lock(lock_file: Path):
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            holder = int(lock_file.read_text().strip() or "0")
        except (ValueError, OSError):
            holder = 0
        if holder and _pid_alive(holder):
            raise AlreadyRunning(f"lock {lock_file} held by pid {holder}")
        lock_file.unlink(missing_ok=True)
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock_file.unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_lock.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_sync/lock.py tests/test_lock.py
git commit -m "feat: lockfile guard against overlapping runs"
```

---

### Task 7: Git helpers (`gitutils.py`)

**Files:**
- Create: `src/claude_sync/gitutils.py`
- Modify: `tests/conftest.py` (add git repo helpers)
- Test: `tests/test_gitutils.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `is_git_repo(dest: Path) -> bool`, `init_repo(dest: Path) -> None`
  - `has_conflict(dest: Path) -> bool` (unmerged entries or `MERGE_HEAD`)
  - `is_diverged(dest: Path) -> bool` (upstream exists AND both sides have unique commits; **never fetches**)
  - `commit_all(dest: Path, message: str) -> bool` (False when nothing to commit)
  - `push(dest: Path) -> bool`
  - `abort_merge(dest: Path) -> None` (no-op when no merge in progress)
  - `merge_keep_local(dest: Path) -> None` (`merge -s ours` with upstream: local tree wins, histories join)
  - `merge_keep_repo(dest: Path) -> None` (merge commit whose tree equals upstream's)
  - `clone(url: str, dest: Path) -> None` (shallow, `--depth 1`)

- [ ] **Step 1: Add git helpers to `tests/conftest.py`**

Append:

```python
import subprocess


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True,
    )


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@test")
    git(path, "config", "user.name", "test")
    return path


@pytest.fixture
def diverged_clones(tmp_path):
    """origin + two clones that have diverged (clone2 knows, via fetch done here)."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    seed = make_repo(tmp_path / "seed")
    (seed / "base.txt").write_text("base")
    git(seed, "add", "base.txt")
    git(seed, "commit", "-m", "base")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-u", "origin", "main")

    clone1, clone2 = tmp_path / "clone1", tmp_path / "clone2"
    for c in (clone1, clone2):
        subprocess.run(["git", "clone", str(origin), str(c)],
                       capture_output=True, check=True)
        git(c, "config", "user.email", "test@test")
        git(c, "config", "user.name", "test")

    (clone1 / "file.txt").write_text("from clone1")
    git(clone1, "add", "file.txt")
    git(clone1, "commit", "-m", "clone1 change")
    git(clone1, "push")

    (clone2 / "file.txt").write_text("from clone2")
    git(clone2, "add", "file.txt")
    git(clone2, "commit", "-m", "clone2 change")
    git(clone2, "fetch")  # clone2 now knows it has diverged
    return clone1, clone2
```

- [ ] **Step 2: Write the failing tests**

`tests/test_gitutils.py`:

```python
from claude_sync import gitutils
from tests.conftest import git, make_repo


def test_is_git_repo(tmp_path):
    assert not gitutils.is_git_repo(tmp_path)
    make_repo(tmp_path / "r")
    assert gitutils.is_git_repo(tmp_path / "r")


def test_init_and_commit_all(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    gitutils.init_repo(repo)
    (repo / "f.txt").write_text("hello")
    assert gitutils.commit_all(repo, "first") is True
    assert gitutils.commit_all(repo, "empty") is False
    log = git(repo, "log", "--oneline").stdout
    assert "first" in log


def test_divergence_detection(diverged_clones):
    clone1, clone2 = diverged_clones
    assert gitutils.is_diverged(clone2) is True
    assert gitutils.is_diverged(clone1) is False


def test_no_upstream_means_not_diverged(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "f").write_text("x")
    git(repo, "add", "f")
    git(repo, "commit", "-m", "c")
    assert gitutils.is_diverged(repo) is False


def test_merge_keep_local(diverged_clones):
    _, clone2 = diverged_clones
    gitutils.merge_keep_local(clone2)
    assert (clone2 / "file.txt").read_text() == "from clone2"
    assert not gitutils.is_diverged(clone2)
    assert gitutils.push(clone2) is True


def test_merge_keep_repo(diverged_clones):
    _, clone2 = diverged_clones
    gitutils.merge_keep_repo(clone2)
    assert (clone2 / "file.txt").read_text() == "from clone1"
    assert not gitutils.is_diverged(clone2)
    assert not gitutils.has_conflict(clone2)


def test_has_conflict_during_real_merge(diverged_clones):
    _, clone2 = diverged_clones
    import subprocess
    subprocess.run(["git", "-C", str(clone2), "merge", "origin/main"],
                   capture_output=True)  # conflicts on file.txt
    assert gitutils.has_conflict(clone2) is True
    gitutils.abort_merge(clone2)
    assert gitutils.has_conflict(clone2) is False


def test_clone(tmp_path, diverged_clones):
    clone1, _ = diverged_clones
    target = tmp_path / "fresh"
    origin_url = git(clone1, "remote", "get-url", "origin").stdout.strip()
    gitutils.clone(origin_url, target)
    assert (target / "base.txt").exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_gitutils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_sync.gitutils'`

- [ ] **Step 4: Implement**

`src/claude_sync/gitutils.py`:

```python
import subprocess
from pathlib import Path


def _git(dest: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(dest), *args], capture_output=True, text=True
    )


def is_git_repo(dest: Path) -> bool:
    p = _git(dest, "rev-parse", "--is-inside-work-tree")
    return p.returncode == 0 and p.stdout.strip() == "true"


def init_repo(dest: Path) -> None:
    _git(dest, "init", "-b", "main")


def has_conflict(dest: Path) -> bool:
    if (dest / ".git" / "MERGE_HEAD").exists():
        return True
    p = _git(dest, "ls-files", "-u")
    return bool(p.stdout.strip())


def _upstream(dest: Path) -> str | None:
    p = _git(dest, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    return p.stdout.strip() if p.returncode == 0 else None


def is_diverged(dest: Path) -> bool:
    upstream = _upstream(dest)
    if not upstream:
        return False
    p = _git(dest, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
    if p.returncode != 0:
        return False
    behind, ahead = (int(n) for n in p.stdout.split())
    return behind > 0 and ahead > 0


def _identity_args(dest: Path) -> list[str]:
    """Fallback identity so commits work on machines with no git config."""
    if _git(dest, "config", "user.email").stdout.strip():
        return []
    return ["-c", "user.name=claude-sync", "-c", "user.email=claude-sync@localhost"]


def commit_all(dest: Path, message: str) -> bool:
    _git(dest, "add", "-A")
    p = _git(dest, *_identity_args(dest), "commit", "-m", message)
    return p.returncode == 0


def push(dest: Path) -> bool:
    return _git(dest, "push").returncode == 0


def abort_merge(dest: Path) -> None:
    if (dest / ".git" / "MERGE_HEAD").exists():
        _git(dest, "merge", "--abort")


def merge_keep_local(dest: Path) -> None:
    upstream = _upstream(dest)
    if upstream:
        _git(dest, *_identity_args(dest), "merge", "-s", "ours", "--no-edit", upstream)


def merge_keep_repo(dest: Path) -> None:
    upstream = _upstream(dest)
    if not upstream:
        return
    _git(dest, "merge", "-s", "ours", "--no-commit", "--no-ff", upstream)
    _git(dest, "read-tree", "-m", "-u", upstream)
    _git(dest, *_identity_args(dest), "commit", "-m", "claude-sync: adopt repo version")


def clone(url: str, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True, text=True, check=True,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_gitutils.py -v`
Expected: 8 PASS

- [ ] **Step 6: Commit**

```bash
git add src/claude_sync/gitutils.py tests/conftest.py tests/test_gitutils.py
git commit -m "feat: git helpers with divergence detection and resolution"
```

---

### Task 8: Backup orchestration (`backup.py`)

**Files:**
- Create: `src/claude_sync/backup.py`
- Test: `tests/test_backup.py`

**Interfaces:**
- Consumes: `Paths`, `load_config`, `save_config`, `SyncConfig` (Task 1); `build_sync_set` (Task 4); `diff_dest`, `apply_changes` (Task 5); `sync_lock`, `AlreadyRunning` (Task 6); `gitutils` (Task 7).
- Produces: `BackupResult(status: str, committed: bool = False, redacted: list[str] = [])` where `status` is one of `"ok"`, `"unchanged"`, `"conflict-pending"`, `"kept-repo"`, `"not-configured"`; `run_backup(paths: Paths, resolver: Callable[[], str | None] | None = None, machine: str | None = None) -> BackupResult`. `resolver` returns `"local"`, `"repo"`, or `None` (cancel). Writes `claude-sync.meta.json` on change. `AlreadyRunning` propagates to the caller.

- [ ] **Step 1: Write the failing tests**

`tests/test_backup.py`:

```python
import json

from claude_sync.backup import run_backup
from claude_sync.config import SyncConfig, load_config, save_config
from tests.conftest import git


def _configure(paths, dest, git_mode=False):
    dest.mkdir(parents=True, exist_ok=True)
    save_config(paths, SyncConfig(destination=str(dest), git_mode=git_mode))


def test_not_configured(fake_claude):
    assert run_backup(fake_claude).status == "not-configured"


def test_plain_backup_mirrors_files(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    _configure(fake_claude, dest)
    result = run_backup(fake_claude)
    assert result.status == "ok"
    assert (dest / "skills" / "my-skill" / "SKILL.md").exists()
    assert (dest / "plugins-manifest.json").exists()
    meta = json.loads((dest / "claude-sync.meta.json").read_text())
    assert meta["schema"] == 1 and "last_sync" in meta and "machine" in meta
    assert result.redacted == ["MY_API_KEY"]
    assert load_config(fake_claude).last_backup is not None


def test_unchanged_backup_is_silent_noop(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    _configure(fake_claude, dest)
    run_backup(fake_claude)
    meta_before = (dest / "claude-sync.meta.json").read_bytes()
    result = run_backup(fake_claude)
    assert result.status == "unchanged"
    assert (dest / "claude-sync.meta.json").read_bytes() == meta_before


def test_git_backup_commits(fake_claude, tmp_path):
    from tests.conftest import make_repo
    dest = make_repo(tmp_path / "dest")
    _configure(fake_claude, dest, git_mode=True)
    result = run_backup(fake_claude, machine="testbox")
    assert result.status == "ok" and result.committed
    log = git(dest, "log", "--oneline").stdout
    assert "claude-sync: testbox" in log
    # second run: no change, no commit
    assert run_backup(fake_claude).status == "unchanged"
    assert git(dest, "log", "--oneline").stdout.count("\n") == 1


def test_conflict_noninteractive_sets_pending(fake_claude, diverged_clones):
    _, clone2 = diverged_clones
    git(clone2, "config", "user.email", "t@t")
    _configure(fake_claude, clone2, git_mode=True)
    result = run_backup(fake_claude, resolver=None)
    assert result.status == "conflict-pending"
    assert load_config(fake_claude).conflict_pending is True


def test_conflict_resolver_keep_local_then_backs_up(fake_claude, diverged_clones):
    _, clone2 = diverged_clones
    _configure(fake_claude, clone2, git_mode=True)
    result = run_backup(fake_claude, resolver=lambda: "local")
    assert result.status == "ok"
    assert load_config(fake_claude).conflict_pending is False
    assert (clone2 / "skills" / "my-skill" / "SKILL.md").exists()


def test_conflict_resolver_keep_repo_skips_backup(fake_claude, diverged_clones):
    _, clone2 = diverged_clones
    _configure(fake_claude, clone2, git_mode=True)
    result = run_backup(fake_claude, resolver=lambda: "repo")
    assert result.status == "kept-repo"
    assert (clone2 / "file.txt").read_text() == "from clone1"
    assert not (clone2 / "skills").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backup.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/backup.py`:

```python
import json
import platform
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from claude_sync import __version__, gitutils
from claude_sync.config import load_config, save_config
from claude_sync.lock import sync_lock
from claude_sync.mirror import apply_changes, diff_dest
from claude_sync.paths import Paths
from claude_sync.syncset import build_sync_set

Resolver = Callable[[], str | None]


@dataclass
class BackupResult:
    status: str
    committed: bool = False
    redacted: list[str] = field(default_factory=list)


def run_backup(
    paths: Paths,
    resolver: Resolver | None = None,
    machine: str | None = None,
) -> BackupResult:
    cfg = load_config(paths)
    if cfg is None:
        return BackupResult(status="not-configured")
    dest = Path(cfg.destination)
    machine = machine or platform.node()

    with sync_lock(paths.lock_file):
        if cfg.git_mode and (gitutils.has_conflict(dest) or gitutils.is_diverged(dest)):
            if resolver is None:
                cfg.conflict_pending = True
                save_config(paths, cfg)
                return BackupResult(status="conflict-pending")
            choice = resolver()
            gitutils.abort_merge(dest)
            if choice == "repo":
                gitutils.merge_keep_repo(dest)
                cfg.conflict_pending = False
                save_config(paths, cfg)
                return BackupResult(status="kept-repo")
            if choice == "local":
                gitutils.merge_keep_local(dest)
            else:
                return BackupResult(status="conflict-pending")

        sync_set = build_sync_set(paths.claude_dir)
        changes = diff_dest(sync_set.files, dest)
        if changes.empty:
            cfg.conflict_pending = False
            save_config(paths, cfg)
            return BackupResult(status="unchanged", redacted=sync_set.redacted_env)

        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        apply_changes(sync_set.files, dest, changes)
        (dest / "claude-sync.meta.json").write_text(json.dumps({
            "schema": 1,
            "tool_version": __version__,
            "last_sync": timestamp,
            "machine": machine,
        }, indent=2) + "\n")

        committed = False
        if cfg.git_mode:
            committed = gitutils.commit_all(
                dest, f"claude-sync: {machine} {timestamp}"
            )
            if cfg.auto_push and not gitutils.push(dest):
                pass  # push failure warns at CLI level via status; commit is safe locally

        cfg.last_backup = timestamp
        cfg.conflict_pending = False
        save_config(paths, cfg)
        return BackupResult(
            status="ok", committed=committed, redacted=sync_set.redacted_env
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backup.py -v`
Expected: 7 PASS

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add src/claude_sync/backup.py tests/test_backup.py
git commit -m "feat: backup orchestration with conflict handling"
```

---

### Task 9: SessionEnd hook (`hook.py`)

**Files:**
- Create: `src/claude_sync/hook.py`
- Test: `tests/test_hook.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (operates on a settings file path directly).
- Produces: `HOOK_SUBSTRING = "claude-sync backup --quiet"`; `hook_command() -> str`; `install_hook(settings_file: Path) -> bool` (False if already installed); `uninstall_hook(settings_file: Path) -> bool` (False if not installed); `is_hook_installed(settings_file: Path) -> bool`. Hook entry shape: `{"hooks": [{"type": "command", "command": hook_command()}]}` appended to `settings["hooks"]["SessionEnd"]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_hook.py`:

```python
import json

from claude_sync.hook import (
    HOOK_SUBSTRING,
    hook_command,
    install_hook,
    is_hook_installed,
    uninstall_hook,
)


def _settings(tmp_path, content):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps(content))
    return f


def test_hook_command_contains_marker():
    assert HOOK_SUBSTRING in hook_command()


def test_install_into_empty_settings(tmp_path):
    f = _settings(tmp_path, {"model": "opus"})
    assert install_hook(f) is True
    data = json.loads(f.read_text())
    entry = data["hooks"]["SessionEnd"][0]
    assert entry["hooks"][0]["type"] == "command"
    assert HOOK_SUBSTRING in entry["hooks"][0]["command"]
    assert data["model"] == "opus"  # rest untouched


def test_install_is_idempotent(tmp_path):
    f = _settings(tmp_path, {})
    install_hook(f)
    assert install_hook(f) is False
    data = json.loads(f.read_text())
    assert len(data["hooks"]["SessionEnd"]) == 1


def test_install_preserves_foreign_hooks(tmp_path):
    foreign = {"hooks": [{"type": "command", "command": "echo other"}]}
    f = _settings(tmp_path, {"hooks": {"SessionEnd": [foreign]}})
    install_hook(f)
    data = json.loads(f.read_text())
    assert len(data["hooks"]["SessionEnd"]) == 2


def test_uninstall_removes_only_ours(tmp_path):
    foreign = {"hooks": [{"type": "command", "command": "echo other"}]}
    f = _settings(tmp_path, {"hooks": {"SessionEnd": [foreign]}})
    install_hook(f)
    assert uninstall_hook(f) is True
    data = json.loads(f.read_text())
    assert data["hooks"]["SessionEnd"] == [foreign]
    assert uninstall_hook(f) is False


def test_is_hook_installed(tmp_path):
    f = _settings(tmp_path, {})
    assert is_hook_installed(f) is False
    install_hook(f)
    assert is_hook_installed(f) is True


def test_install_when_settings_missing(tmp_path):
    f = tmp_path / "settings.json"
    assert install_hook(f) is True
    assert is_hook_installed(f) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hook.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/hook.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hook.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_sync/hook.py tests/test_hook.py
git commit -m "feat: SessionEnd hook install/uninstall"
```

---

### Task 10: Restore orchestration (`restore.py`)

**Files:**
- Create: `src/claude_sync/restore.py`
- Test: `tests/test_restore.py`

**Interfaces:**
- Consumes: `Paths`, `SyncConfig`, `save_config`, `load_config` (Task 1); `REDACTED` (Task 2); `marketplace_add_arg` (Task 3); `MANAGED_DIRS`, `MANAGED_FILES` (Task 5); `gitutils.clone`, `gitutils.is_git_repo` (Task 7).
- Produces: `RestoreResult(restored: list[str], failed_plugins: list[tuple[str, str]], redacted_env: list[str], safety_dir: Path | None)` and `run_restore(paths: Paths, source: str | None, to: Path | None = None, run=subprocess.run) -> RestoreResult`. Raises `RestoreError(Exception)` for a missing/invalid source. `run` is injected so tests stub the `claude` CLI.

- [ ] **Step 1: Write the failing tests**

`tests/test_restore.py`:

```python
import json
from types import SimpleNamespace

import pytest

from claude_sync.backup import run_backup
from claude_sync.config import SyncConfig, load_config, save_config
from claude_sync.paths import Paths
from claude_sync.redact import REDACTED
from claude_sync.restore import RestoreError, run_restore


@pytest.fixture
def backup_dir(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    save_config(fake_claude, SyncConfig(destination=str(dest)))
    run_backup(fake_claude)
    return dest


def _fake_run_factory(calls, fail_for=()):
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        name = cmd[-1]
        if name in fail_for:
            return SimpleNamespace(returncode=1, stdout="", stderr=f"no such plugin {name}")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return fake_run


def test_restore_onto_fresh_machine(backup_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
    new_home = tmp_path / "home2"
    paths = Paths(home=new_home)
    calls = []
    result = run_restore(paths, str(backup_dir), run=_fake_run_factory(calls))
    assert (paths.claude_dir / "skills" / "my-skill" / "SKILL.md").exists()
    assert (paths.claude_dir / "CLAUDE.md").exists()
    settings = json.loads(paths.settings_file.read_text())
    assert settings["env"]["MY_API_KEY"] == REDACTED
    assert result.redacted_env == ["MY_API_KEY"]
    assert result.failed_plugins == []
    # marketplace added, both plugins installed
    assert ["/usr/bin/claude", "plugin", "marketplace", "add",
            "anthropics/claude-plugins-official"] in calls
    installs = [c for c in calls if c[1:3] == ["plugin", "install"]]
    assert len(installs) == 2
    # machine is configured for future backups
    cfg = load_config(paths)
    assert cfg.destination == str(backup_dir)
    assert result.safety_dir is None  # nothing pre-existing


def test_restore_saves_safety_copy_of_overwritten_files(backup_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    new_home = tmp_path / "home2"
    paths = Paths(home=new_home)
    paths.claude_dir.mkdir(parents=True)
    (paths.claude_dir / "CLAUDE.md").write_text("old local content")
    result = run_restore(paths, str(backup_dir), run=_fake_run_factory([]))
    assert result.safety_dir is not None
    assert (result.safety_dir / "CLAUDE.md").read_text() == "old local content"
    assert (paths.claude_dir / "CLAUDE.md").read_text() == "global instructions\n"


def test_restore_plugin_failure_is_fail_soft(backup_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
    paths = Paths(home=tmp_path / "home2")
    calls = []
    result = run_restore(
        paths, str(backup_dir),
        run=_fake_run_factory(calls, fail_for={"swift-lsp@claude-plugins-official"}),
    )
    assert len(result.failed_plugins) == 1
    assert result.failed_plugins[0][0] == "swift-lsp@claude-plugins-official"
    assert len([c for c in calls if c[1:3] == ["plugin", "install"]]) == 2


def test_restore_without_claude_cli_reports_all_plugins_failed(backup_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    paths = Paths(home=tmp_path / "home2")
    result = run_restore(paths, str(backup_dir), run=_fake_run_factory([]))
    assert len(result.failed_plugins) == 2
    assert all("claude CLI not found" in err for _, err in result.failed_plugins)


def test_restore_missing_source_raises(tmp_path):
    paths = Paths(home=tmp_path / "home2")
    with pytest.raises(RestoreError):
        run_restore(paths, str(tmp_path / "nope"))
    with pytest.raises(RestoreError):
        run_restore(paths, None)  # no source and not configured
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_restore.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/restore.py`:

```python
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
    return source.startswith(("http://", "https://", "git@", "ssh://"))


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
        gitutils.clone(source, src)
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

    save_config(paths, SyncConfig(
        destination=str(src), git_mode=gitutils.is_git_repo(src)
    ))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_restore.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_sync/restore.py tests/test_restore.py
git commit -m "feat: restore with safety copy and plugin reinstall"
```

---

### Task 11: Status (`statuscmd.py`)

**Files:**
- Create: `src/claude_sync/statuscmd.py`
- Test: `tests/test_statuscmd.py`

**Interfaces:**
- Consumes: `Paths`, `load_config` (Task 1); `build_sync_set` (Task 4); `diff_dest` (Task 5); `is_hook_installed` (Task 9).
- Produces: `StatusInfo(configured: bool, destination: str | None, git_mode: bool, last_backup: str | None, conflict_pending: bool, hook_installed: bool, dirty: bool, redacted_env: list[str])`; `gather_status(paths: Paths) -> StatusInfo`; `render_status(info: StatusInfo) -> str` (plain multi-line string; CLI prints it).

- [ ] **Step 1: Write the failing tests**

`tests/test_statuscmd.py`:

```python
from claude_sync.backup import run_backup
from claude_sync.config import SyncConfig, save_config
from claude_sync.hook import install_hook
from claude_sync.statuscmd import gather_status, render_status


def test_status_unconfigured(fake_claude):
    info = gather_status(fake_claude)
    assert info.configured is False
    assert "not configured" in render_status(info).lower()


def test_status_after_backup_is_clean(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    save_config(fake_claude, SyncConfig(destination=str(dest)))
    run_backup(fake_claude)
    info = gather_status(fake_claude)
    assert info.configured and not info.dirty
    assert info.last_backup is not None
    assert info.redacted_env == ["MY_API_KEY"]
    assert info.hook_installed is False


def test_status_detects_drift_and_hook(fake_claude, tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    save_config(fake_claude, SyncConfig(destination=str(dest)))
    run_backup(fake_claude)
    (fake_claude.claude_dir / "skills" / "new-skill").mkdir()
    (fake_claude.claude_dir / "skills" / "new-skill" / "SKILL.md").write_text("new")
    install_hook(fake_claude.settings_file)
    info = gather_status(fake_claude)
    assert info.dirty is True
    assert info.hook_installed is True
    text = render_status(info)
    assert "MY_API_KEY" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_statuscmd.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/statuscmd.py`:

```python
from dataclasses import dataclass, field
from pathlib import Path

from claude_sync.config import load_config
from claude_sync.hook import is_hook_installed
from claude_sync.mirror import diff_dest
from claude_sync.paths import Paths
from claude_sync.syncset import build_sync_set


@dataclass
class StatusInfo:
    configured: bool
    destination: str | None = None
    git_mode: bool = False
    last_backup: str | None = None
    conflict_pending: bool = False
    hook_installed: bool = False
    dirty: bool = False
    redacted_env: list[str] = field(default_factory=list)


def gather_status(paths: Paths) -> StatusInfo:
    cfg = load_config(paths)
    if cfg is None:
        return StatusInfo(configured=False)
    sync_set = build_sync_set(paths.claude_dir)
    changes = diff_dest(sync_set.files, Path(cfg.destination))
    return StatusInfo(
        configured=True,
        destination=cfg.destination,
        git_mode=cfg.git_mode,
        last_backup=cfg.last_backup,
        conflict_pending=cfg.conflict_pending,
        hook_installed=is_hook_installed(paths.settings_file),
        dirty=not changes.empty,
        redacted_env=sync_set.redacted_env,
    )


def render_status(info: StatusInfo) -> str:
    if not info.configured:
        return "claude-sync is not configured. Run: claude-sync init"
    lines = [
        f"Destination:      {info.destination} ({'git' if info.git_mode else 'plain folder'})",
        f"Last backup:      {info.last_backup or 'never'}",
        f"Local changes:    {'yes — run claude-sync backup' if info.dirty else 'none (in sync)'}",
        f"Session-end hook: {'installed' if info.hook_installed else 'not installed'}",
    ]
    if info.conflict_pending:
        lines.append("CONFLICT PENDING: run claude-sync resolve to choose a version")
    if info.redacted_env:
        lines.append("Redacted env vars (re-supply after restore): "
                     + ", ".join(info.redacted_env))
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_statuscmd.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_sync/statuscmd.py tests/test_statuscmd.py
git commit -m "feat: status gathering and rendering"
```

---

### Task 12: Init wizard (`wizard.py`)

**Files:**
- Create: `src/claude_sync/wizard.py`
- Test: `tests/test_wizard.py`

**Interfaces:**
- Consumes: `Paths`, `SyncConfig`, `save_config`, `load_config` (Task 1); `gitutils.is_git_repo`, `gitutils.init_repo` (Task 7); `run_backup` (Task 8); `install_hook` (Task 9).
- Produces: `Prompts` protocol with methods `ask_destination(default: str) -> str`, `confirm(message: str, default: bool = True) -> bool`, `info(message: str) -> None`; `run_init(paths: Paths, destination: str | None, yes: bool, prompts: Prompts) -> int` (exit code). `yes=True` answers every confirm with its default and requires no prompts object interaction beyond `info`. The multi-machine divergence note (spec wording) is emitted via `prompts.info` whenever git mode ends up enabled.

- [ ] **Step 1: Write the failing tests**

`tests/test_wizard.py`:

```python
from claude_sync.config import load_config
from claude_sync.hook import is_hook_installed
from claude_sync.wizard import run_init
from tests.conftest import make_repo


class ScriptedPrompts:
    def __init__(self, destination=None, answers=None):
        self.destination = destination
        self.answers = dict(answers or {})
        self.infos = []

    def ask_destination(self, default):
        return self.destination or default

    def confirm(self, message, default=True):
        for key, value in self.answers.items():
            if key in message.lower():
                return value
        return default

    def info(self, message):
        self.infos.append(message)


def test_init_yes_mode_plain_folder(fake_claude, tmp_path):
    dest = tmp_path / "backup"
    code = run_init(fake_claude, str(dest), yes=True, prompts=ScriptedPrompts())
    assert code == 0
    cfg = load_config(fake_claude)
    assert cfg.destination == str(dest)
    assert cfg.git_mode is True  # --yes accepts the git-init default
    assert (dest / "plugins-manifest.json").exists()
    assert is_hook_installed(fake_claude.settings_file)


def test_init_decline_git_and_hook(fake_claude, tmp_path):
    dest = tmp_path / "backup"
    prompts = ScriptedPrompts(
        destination=str(dest),
        answers={"git repository": False, "hook": False},
    )
    code = run_init(fake_claude, None, yes=False, prompts=prompts)
    assert code == 0
    cfg = load_config(fake_claude)
    assert cfg.git_mode is False
    assert not is_hook_installed(fake_claude.settings_file)


def test_init_existing_git_repo_warns_about_divergence(fake_claude, tmp_path):
    dest = make_repo(tmp_path / "repo")
    prompts = ScriptedPrompts(destination=str(dest))
    run_init(fake_claude, None, yes=False, prompts=prompts)
    cfg = load_config(fake_claude)
    assert cfg.git_mode is True
    assert any("diverge" in msg for msg in prompts.infos)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_wizard.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/wizard.py`:

```python
from pathlib import Path
from typing import Protocol

from claude_sync import gitutils
from claude_sync.backup import run_backup
from claude_sync.config import SyncConfig, save_config
from claude_sync.hook import install_hook
from claude_sync.paths import Paths

DIVERGENCE_NOTE = (
    "Note: if you back up from multiple machines to the same repo, their "
    "histories can diverge. claude-sync never merges automatically — it "
    "detects divergence and walks you through choosing which version to keep."
)


class Prompts(Protocol):
    def ask_destination(self, default: str) -> str: ...
    def confirm(self, message: str, default: bool = True) -> bool: ...
    def info(self, message: str) -> None: ...


def run_init(paths: Paths, destination: str | None, yes: bool, prompts: Prompts) -> int:
    default_dest = str(paths.home / "claude-backup")
    dest_input = destination or (
        default_dest if yes else prompts.ask_destination(default_dest)
    )
    dest = Path(dest_input).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    if gitutils.is_git_repo(dest):
        git_mode = yes or prompts.confirm(
            "Treat this as a git-backed destination? "
            "Commits will be made automatically.", default=True,
        )
    else:
        git_mode = yes or prompts.confirm(
            "Initialize a git repository here so backups get history?",
            default=True,
        )
        if git_mode:
            gitutils.init_repo(dest)
    if git_mode:
        prompts.info(DIVERGENCE_NOTE)

    save_config(paths, SyncConfig(destination=str(dest), git_mode=git_mode))

    if yes or prompts.confirm(
        "Install the Claude Code session-end hook so backups run automatically?",
        default=True,
    ):
        install_hook(paths.settings_file)

    result = run_backup(paths)
    prompts.info(f"First backup: {result.status} → {dest}")
    if result.redacted:
        prompts.info(
            "Redacted from settings.json (never leaves this machine): "
            + ", ".join(result.redacted)
        )
    return 0 if result.status in ("ok", "unchanged") else 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_wizard.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_sync/wizard.py tests/test_wizard.py
git commit -m "feat: init wizard flow behind testable Prompts protocol"
```

---

### Task 13: CLI (`cli.py`)

**Files:**
- Create: `src/claude_sync/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above. Entry point `claude-sync = "claude_sync.cli:main"` already declared in Task 1.
- Produces: `main(argv: list[str] | None = None) -> int`; `build_paths() -> Paths` (reads `CLAUDE_SYNC_HOME` env var override, else `Path.home()` — this is how tests and the end-to-end task point the CLI at a sandbox); `InteractivePrompts` (rich + questionary implementation of the `Prompts` protocol); `interactive_resolver() -> str | None` (questionary select returning `"local"` / `"repo"` / `None`).

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
import json

from claude_sync.cli import main
from claude_sync.config import load_config


def _env_home(monkeypatch, home):
    monkeypatch.setenv("CLAUDE_SYNC_HOME", str(home))


def test_backup_not_configured_exits_nonzero(fake_claude, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    assert main(["backup"]) == 1
    assert "init" in capsys.readouterr().err


def test_init_yes_then_backup_then_status(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    dest = tmp_path / "dest"
    assert main(["init", str(dest), "--yes"]) == 0
    assert load_config(fake_claude) is not None
    assert main(["backup"]) == 0  # unchanged → still exit 0
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Destination" in out


def test_backup_quiet_prints_nothing_when_unchanged(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    main(["init", str(tmp_path / "dest"), "--yes"])
    capsys.readouterr()
    assert main(["backup", "--quiet"]) == 0
    out = capsys.readouterr()
    assert out.out == ""


def test_backup_show_redactions(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    main(["init", str(tmp_path / "dest"), "--yes"])
    (fake_claude.claude_dir / "CLAUDE.md").write_text("changed\n")
    capsys.readouterr()
    assert main(["backup", "--show-redactions"]) == 0
    assert "MY_API_KEY" in capsys.readouterr().out


def test_hook_install_uninstall(fake_claude, tmp_path, monkeypatch):
    _env_home(monkeypatch, fake_claude.home)
    main(["init", str(tmp_path / "dest"), "--yes"])
    assert main(["hook", "uninstall"]) == 0
    settings = json.loads(fake_claude.settings_file.read_text())
    assert settings["hooks"]["SessionEnd"] == []
    assert main(["hook", "install"]) == 0


def test_restore_via_cli(fake_claude, tmp_path, monkeypatch, capsys):
    _env_home(monkeypatch, fake_claude.home)
    dest = tmp_path / "dest"
    main(["init", str(dest), "--yes"])
    home2 = tmp_path / "home2"
    _env_home(monkeypatch, home2)
    monkeypatch.setattr("shutil.which", lambda name: None)  # no claude CLI
    assert main(["restore", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "MY_API_KEY" in out  # redaction checklist printed
    assert (home2 / ".claude" / "CLAUDE.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/claude_sync/cli.py`:

```python
import argparse
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
        run_backup(paths)  # destination must reflect the settings change
        return 0
    return 2


class _SilentPrompts:
    def ask_destination(self, default: str) -> str:
        return default

    def confirm(self, message: str, default: bool = True) -> bool:
        return default

    def info(self, message: str) -> None:
        print(message)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 6 PASS

- [ ] **Step 5: Sanity-check the console script**

Run: `uv run claude-sync --help`
Expected: usage text listing init, backup, restore, status, resolve, hook

- [ ] **Step 6: Commit**

```bash
git add src/claude_sync/cli.py tests/test_cli.py
git commit -m "feat: argparse CLI with interactive prompts and resolver"
```

---

### Task 14: End-to-end smoke test and README

**Files:**
- Create: `tests/test_end_to_end.py`, rewrite `README.md`
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `main` (Task 13) and the `fake_claude` fixture (Task 3).
- Produces: proof that the full loop works: init → change → hook-style quiet backup → git history → restore onto a second "machine".

- [ ] **Step 1: Write the end-to-end test**

`tests/test_end_to_end.py`:

```python
import json

from claude_sync.cli import main
from claude_sync.paths import Paths
from claude_sync.redact import REDACTED
from tests.conftest import git


def test_full_lifecycle(fake_claude, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_SYNC_HOME", str(fake_claude.home))
    dest = tmp_path / "backup-repo"

    # Machine 1: init (git mode via --yes defaults), first backup committed
    assert main(["init", str(dest), "--yes"]) == 0
    assert "claude-sync:" in git(dest, "log", "--oneline").stdout

    # settings change → quiet (hook-style) backup makes a second commit
    settings = json.loads(fake_claude.settings_file.read_text())
    settings["model"] = "sonnet"
    fake_claude.settings_file.write_text(json.dumps(settings))
    assert main(["backup", "--quiet"]) == 0
    assert git(dest, "log", "--oneline").stdout.count("\n") >= 2

    # no history ever leaked into the backup
    backed_up = {p.name for p in dest.rglob("*") if p.is_file()}
    assert "history.jsonl" not in backed_up
    raw = b"".join(p.read_bytes() for p in dest.rglob("*.json") if p.is_file())
    assert b"supersecret" not in raw

    # Machine 2: one-command restore
    home2 = tmp_path / "home2"
    monkeypatch.setenv("CLAUDE_SYNC_HOME", str(home2))
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert main(["restore", str(dest)]) == 0
    paths2 = Paths(home=home2)
    restored = json.loads(paths2.settings_file.read_text())
    assert restored["model"] == "sonnet"
    assert restored["env"]["MY_API_KEY"] == REDACTED
    assert (paths2.claude_dir / "skills" / "my-skill" / "SKILL.md").exists()

    # Machine 2 is configured; unchanged backup is a no-op
    assert main(["backup"]) == 0
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_end_to_end.py -v`
Expected: PASS (if it fails, the bug is real — fix the involved module, not the test)

- [ ] **Step 3: Write `README.md`**

```markdown
# claude-sync

Back up and restore your Claude Code configuration — skills, hooks, agents,
keybindings, global CLAUDE.md, a redacted settings.json, and a plugin
manifest. Never your history, sessions, or projects.

## Quick start

Set up backups on the machine you already use:

    uvx claude-sync init

Reproduce your setup on a new machine (one command):

    uvx claude-sync restore https://github.com/you/claude-backup.git

## Commands

| Command | What it does |
|---|---|
| `claude-sync init [dest]` | Interactive setup: choose destination, git mode, auto-backup hook |
| `claude-sync backup` | One sync pass (no-op when nothing changed; commits in git mode) |
| `claude-sync restore [src]` | Restore from a directory or git URL; reinstalls plugins |
| `claude-sync status` | Destination, last backup, drift, pending conflicts |
| `claude-sync resolve` | Choose a version when two machines diverged |
| `claude-sync hook install\|uninstall` | Manage the SessionEnd auto-backup hook |

## What about secrets?

Env vars in `settings.json` whose names look sensitive (`*KEY*`, `*TOKEN*`,
`*SECRET*`, `*PASSWORD*`, `*CREDENTIAL*`) or whose values look like
credentials are replaced with `<redacted-by-claude-sync>` before anything
leaves your machine. `claude-sync status` lists what you need to re-supply
after a restore.

## Multi-machine use

Backups from several machines to one git repo can diverge. claude-sync never
merges on its own: it detects divergence, skips the automatic backup, and
`claude-sync resolve` lets you pick which version to keep. The losing
version stays in git history.
```

- [ ] **Step 4: Run the whole suite one last time**

Run: `uv run pytest -q`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_end_to_end.py README.md
git commit -m "test: end-to-end lifecycle smoke test; document usage in README"
```

---

## Deviations From Spec (intentional, minor)

- **Diff mechanics:** the spec says "size + mtime, content hash on mismatch". Because the sync set is built in memory, `diff_dest` compares size then exact bytes — strictly more accurate, same intent, less machinery.
- **Mid-merge resolution:** any in-progress merge is first aborted, reducing both conflict scenarios to the diverged case, then resolved with `merge -s ours` (keep local) or an `ours`-merge whose tree is reset to upstream (keep repo). Both produce a proper merge commit, so the losing version stays in history exactly as the spec promises.

## Not In This Plan (spec'd but deferred to release time)

- Publishing to PyPI (build + `uv publish`) — do after the tool has been used locally for a few days.
- Auto-push (`git.auto_push`) is implemented in config and backup but has no CLI toggle; users can edit `~/.claude-sync.json`. Add `claude-sync config` later if wanted.
