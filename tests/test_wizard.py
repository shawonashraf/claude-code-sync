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


def test_init_refuses_claude_dir_destination(fake_claude):
    settings_before = fake_claude.settings_file.read_text()
    code = run_init(
        fake_claude, str(fake_claude.claude_dir), yes=True, prompts=ScriptedPrompts()
    )
    assert code == 1
    assert load_config(fake_claude) is None
    assert fake_claude.settings_file.read_text() == settings_before


def test_init_with_resolver_resolves_conflict(fake_claude, diverged_clones):
    _, clone2 = diverged_clones
    code = run_init(
        fake_claude, str(clone2), yes=False, prompts=ScriptedPrompts(),
        resolver=lambda: "local",
    )
    assert code == 0
    assert (clone2 / "skills" / "my-skill" / "SKILL.md").exists()


def test_init_without_remote_leaves_auto_push_off(fake_claude, tmp_path):
    run_init(fake_claude, str(tmp_path / "backup"), yes=True, prompts=ScriptedPrompts())
    assert load_config(fake_claude).auto_push is False


def test_init_with_remote_defaults_auto_push_on(fake_claude, diverged_clones):
    clone1, _ = diverged_clones
    prompts = ScriptedPrompts(destination=str(clone1))
    run_init(fake_claude, None, yes=False, prompts=prompts)
    assert load_config(fake_claude).auto_push is True


def test_init_with_remote_can_decline_auto_push(fake_claude, diverged_clones):
    clone1, _ = diverged_clones
    prompts = ScriptedPrompts(destination=str(clone1), answers={"push": False})
    run_init(fake_claude, None, yes=False, prompts=prompts)
    assert load_config(fake_claude).auto_push is False


def test_init_explicit_flag_overrides_remote_default(fake_claude, diverged_clones):
    clone1, _ = diverged_clones
    run_init(fake_claude, str(clone1), yes=True, prompts=ScriptedPrompts(),
             auto_push=False)
    assert load_config(fake_claude).auto_push is False
