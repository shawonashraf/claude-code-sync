import copy
import re

REDACTED = "<redacted-by-claude-sync>"

_SENSITIVE_NAME = re.compile(r"key|token|secret|password|credential", re.IGNORECASE)
_SECRET_PREFIX = re.compile(r"^(sk-|ghp_|gho_|github_pat_|glpat-|xox[a-z]-|AKIA)")
_BASE64ISH = re.compile(r"^[A-Za-z0-9+/=_\-]{32,}$")
_JWT_SHAPE = re.compile(r"^eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*$")
_URL_USERINFO = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


def _looks_like_secret(value: str) -> bool:
    if _SECRET_PREFIX.match(value):
        return True
    if _JWT_SHAPE.match(value):
        return True
    if _URL_USERINFO.search(value):
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
