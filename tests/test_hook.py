import json

from claude_sync.hook import (
    hook_command,
    install_hook,
    is_hook_command,
    is_hook_installed,
    uninstall_hook,
)


def _settings(tmp_path, content):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps(content))
    return f


def test_hook_command_contains_marker():
    assert is_hook_command(hook_command())


def test_install_into_empty_settings(tmp_path):
    f = _settings(tmp_path, {"model": "opus"})
    assert install_hook(f) is True
    data = json.loads(f.read_text())
    entry = data["hooks"]["SessionEnd"][0]
    assert entry["hooks"][0]["type"] == "command"
    assert is_hook_command(entry["hooks"][0]["command"])
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


def test_installed_entry_is_async_with_timeout(tmp_path):
    f = tmp_path / "settings.json"
    install_hook(f)
    entry = json.loads(f.read_text())["hooks"]["SessionEnd"][0]["hooks"][0]
    assert entry["async"] is True
    assert entry["timeout"] == 60
