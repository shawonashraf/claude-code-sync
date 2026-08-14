import json
import subprocess

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
