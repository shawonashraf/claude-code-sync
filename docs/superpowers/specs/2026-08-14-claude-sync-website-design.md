# claude-sync Website & PyPI Release — Design Spec

**Date:** 2026-08-14
**Status:** Approved design
**Depends on:** docs/superpowers/specs/2026-08-14-claude-sync-design.md (the tool this site documents)

## Purpose

Give new users a thorough, friendly onboarding site for claude-sync, hosted
on GitHub Pages and deployed by GitHub Actions. Publish the package to PyPI
first so every command the site teaches (`uvx claude-sync …`) works verbatim.

## Decisions (agreed during brainstorming)

| Question | Decision |
|---|---|
| Site generator | MkDocs Material (fits the Python/uv stack) |
| Content scope | Full onboarding set, 7 pages |
| Deploy | Official GitHub Pages actions (build in CI, `actions/deploy-pages`, no gh-pages branch) |
| License | MIT |
| PyPI | Publish 0.1.0 with `uv publish --token $PYPI_TOKEN` before the site ships |
| Execution | Inline (no per-task subagents); spec committed, no separate plan doc |

## Part 1: PyPI release (prerequisite)

- Add `LICENSE` (MIT, Shawon Ashraf).
- `pyproject.toml` additions: `license = "MIT"`, `authors`, `[project.urls]`
  (Repository → https://github.com/shawonashraf/claude-sync, Documentation →
  https://shawonashraf.github.io/claude-sync/), classifiers (Python 3.13,
  Environment :: Console, Topic :: Utilities, License :: OSI Approved :: MIT License).
- `uv build`, then `uv publish --token $PYPI_TOKEN`.
- Verify from PyPI with a clean `uvx claude-sync --help`.
- Version stays 0.1.0 for this first release.

## Part 2: Site structure

`docs_dir` is `website/` — deliberately not the existing `docs/`, which holds
internal specs/plans that must not publish.

```
mkdocs.yml
website/
  index.md            # landing: hero, one-line pitch, 3-step quick start, what's synced / never synced
  getting-started.md  # install (uvx/pipx tabs), init walkthrough, hook setup
  backup-restore.md   # backup mechanics (redaction, manifest, no-op runs), new-machine restore, safety copy
  multi-machine.md    # divergence, conflict detection, resolve flow, auto_push
  security.md         # what leaves the machine, redaction rules (names, prefixes, entropy, JWT, URL creds), placeholder + checklist, no history/sessions ever
  commands.md         # all six commands, every flag, exit codes
  faq.md              # troubleshooting: hook not firing, conflict-pending, failed plugin installs, held lock, unreachable destination
  stylesheets/extra.css
```

Content is written from the tool's spec and actual CLI behavior (flags
verified against `cli.py`). Onboarding voice: each page opens with what the
reader accomplishes; commands are copy-paste blocks with expected output.

## Part 3: Theming

- Material palette: light and dark schemes with toggle; warm amber/copper
  accent instead of default indigo.
- Landing hero (title, pitch, Get started / GitHub buttons, quick-start
  block) via Markdown + ~30 lines of `extra.css`. No HTML template overrides.
- Features: `navigation.sections`, `navigation.footer`, `content.code.copy`,
  `search.suggest`, admonitions, tabbed code blocks.
- `site_url: https://shawonashraf.github.io/claude-sync/`; repo link in header.
- No extra build plugins beyond `mkdocs-material`.

## Part 4: Deploy workflow and repo wiring

- `pyproject.toml`: `[dependency-groups] docs = ["mkdocs-material>=9"]`.
- `.github/workflows/docs.yml`: on push to `main` (paths `website/**`,
  `mkdocs.yml`, the workflow file) + `workflow_dispatch`. Build job:
  checkout → `astral-sh/setup-uv` → `uv run --group docs mkdocs build --strict`
  → `actions/upload-pages-artifact` (`site/`). Deploy job:
  `actions/deploy-pages`, `github-pages` environment, `pages: write` +
  `id-token: write` permissions.
- Repo Pages source set to "GitHub Actions" via `gh api`.
- `.gitignore`: add `site/`.

## Testing

- Local `mkdocs build --strict` (broken links fail) before commit.
- After push: watch the Actions run, then fetch the live URL and verify it renders.

## Out of Scope

- Custom domain, analytics, versioned docs, blog.
- Changing tool behavior (docs-only, plus packaging metadata).
