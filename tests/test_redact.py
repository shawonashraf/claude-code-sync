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


def test_redacts_jwt_and_url_credentials():
    settings = {"env": {
        "AUTH": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        "DATABASE_URL": "postgres://admin:SuperSecretPass123@db.example.com:5432/prod",
        "WEBSITE": "https://example.com/path",  # benign URL, should NOT be redacted
    }}
    redacted, names = redact_settings(settings)
    assert redacted["env"]["AUTH"] == REDACTED
    assert redacted["env"]["DATABASE_URL"] == REDACTED
    assert redacted["env"]["WEBSITE"] == "https://example.com/path"  # unchanged
    assert names == ["AUTH", "DATABASE_URL"]


def test_lowercase_sensitive_name_is_redacted():
    settings = {"env": {"my_api_key": "benign_value"}}
    redacted, names = redact_settings(settings)
    assert redacted["env"]["my_api_key"] == REDACTED
    assert names == ["my_api_key"]
