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
