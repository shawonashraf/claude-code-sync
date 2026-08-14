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
