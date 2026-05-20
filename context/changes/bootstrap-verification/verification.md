---
bootstrapped_at: 2026-05-20T18:02:43Z
starter_id: django
starter_name: Django
project_name: melo-gierka
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: verified
phase_3_status: ok
audit_command: pip-audit
---

## Hand-off

Verbatim copy of `context/foundation/tech-stack.md`:

```yaml
starter_id: django
package_manager: uv
project_name: melo-gierka
hints:
  language_family: python
  team_size: solo
  deployment_target: fly
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: verified
  path_taken: standard
  quality_override: false
  self_check_answers: null
  has_auth: false
  has_payments: false
  has_realtime: true
  has_ai: false
  has_background_jobs: false
```

### Why this stack

Solo developer building a real-time party music game in 4 weeks, targeting kilkanaście znajomych as the user base. Standard path — Django is the recommended default for `(web, python)` and clears all four agent-friendly gates within the Python training corpus. The product needs a server that handles ephemeral session state (10-round game lifecycle, ~7 min), a polling endpoint sustaining ≤ 1s UI sync between host and players, and a simple mobile HTML join page — Django's batteries-included posture (templates, session middleware, JSON responses) covers all three without external libraries. Real-time is needed (`has_realtime: true`) but implemented as HTTP polling, not WebSockets, which Django handles cleanly in its synchronous model. The streaming audio layer is JS-only in the host's browser and orthogonal to backend language. Fly.io is Django's first deployment default and free at MeloGierka's scale (hobby tier). CI on GitHub Actions with auto-deploy-on-merge — what the starter ships with. The ORM, admin, and migrations Django bundles are unused for ephemeral sessions; that bloat is the accepted cost for staying on the framework's verified path.

## Pre-scaffold verification

| Signal       | Value                                                      | Severity | Notes                                                                                |
| ------------ | ---------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------ |
| npm package  | not run                                                    | n/a      | Django is not a JS-family starter; `cmd_template` is not a `create-*` npm CLI        |
| GitHub repo  | not run                                                    | n/a      | card `docs_url` is `docs.djangoproject.com`, not a `github.com/<owner>/<repo>` URL   |

No recency signal available per `pre-scaffold-verification.md`'s rule for non-GitHub `docs_url`. Card-side metadata (`last_updated: 2026-04-20`) indicates the registry entry itself is fresh.

## Scaffold log

**Resolved invocation**: `uv init --name melo-gierka && uv add django && uv run django-admin startproject melo_gierka .`
**Strategy**: native-cwd
**Exit code**: 0
**Pre-flight files-to-touch**: `pyproject.toml`, `main.py`, `.python-version`, `.gitignore`, `.git/`, `.venv/`, `uv.lock`, `README.md` (from `uv init`); `manage.py`, `melo_gierka/__init__.py`, `melo_gierka/settings.py`, `melo_gierka/urls.py`, `melo_gierka/wsgi.py`, `melo_gierka/asgi.py` (from `django-admin startproject`)
**Files written by CLI**: 14
**Pre-existing files preserved**: `.claude/`, `.DS_Store`, `CLAUDE.md`, `context/`, `project-idea.md`

Notes on the resolved invocation:

- The card's `cmd_template` is `django-admin startproject {name} .`. The strict native-cwd substitution would render `{name}` → `.`, which Django rejects (project names must be valid Python identifiers). Pragmatic substitution used: `{name}` → `melo_gierka` (the hand-off's `project_name` with the hyphen normalized to an underscore per Python identifier rules). The `.` literal at the end of the template is the destination directory and is preserved verbatim.
- The card's `pre` step (`pip install django`) was translated to uv idioms (`uv init --name melo-gierka && uv add django`) because the hand-off's `package_manager` is `uv`. Functionally equivalent: Django ends up installed and runnable.
- `uv` itself was not installed on the system at invocation time; it was installed via the official installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`) before the scaffold ran. Installed version: `0.11.15` to `~/.local/bin`.
- `uv init` initialised a fresh `.git/` repo in cwd. Unlike the `git-clone` strategy, native-cwd does not auto-delete `.git/` — the repo is the user's to keep, reset, or replace.
- No conflict matrix application: native-cwd writes directly; no `.scaffold` siblings produced. No pre-existing file was overwritten by either `uv init` or `django-admin startproject`.

## Post-scaffold audit

**Tool**: `pip-audit --format json` (run via `.venv/bin/pip-audit` after `uv pip install pip-audit` into the project venv)
**Summary**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW
**Direct vs transitive**: not distinguished by this tool

Clean tree. The project venv at audit time held 32 packages: django 5.2.14 (direct) and its transitive deps `asgiref 3.11.1`, `sqlparse 0.5.5`, `typing-extensions 4.15.0`; plus pip-audit 2.10.0 and its support deps (installed into the venv to perform the audit). No advisories were returned by the OSV / PyPI vulnerability database for any package.

Note: an initial `uvx pip-audit` invocation audited the ephemeral uvx tool environment rather than the project venv (no `django` listed in its dependency report). The re-run via `.venv/bin/pip-audit` is the authoritative finding above.

## Hints recorded but not acted on

| Hint                       | Value                          |
| -------------------------- | ------------------------------ |
| bootstrapper_confidence    | verified                       |
| quality_override           | false                          |
| path_taken                 | standard                       |
| self_check_answers         | null                           |
| team_size                  | solo                           |
| deployment_target          | fly                            |
| ci_provider                | github-actions                 |
| ci_default_flow            | auto-deploy-on-merge           |
| has_auth                   | false                          |
| has_payments               | false                          |
| has_realtime               | true                           |
| has_ai                     | false                          |
| has_background_jobs        | false                          |

Per `handoff-consumer.md`, these fields are surfaced in conversation and logged here but produce no automated action in v1. CI workflow scaffolding (`github-actions` + `auto-deploy-on-merge`), the Fly deployment target, and the `has_realtime: true` feature flag are all carried forward without action — a future M1L4 skill (or a later bootstrapper revision) is the intended consumer.

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- `git init` is not needed — `uv init` already created a `.git/` in cwd. Decide whether to keep that history start, `rm -rf .git && git init` to reset, or commit the scaffold as the first commit.
- No `.scaffold` siblings were created this run, so no conflict-policy decisions are pending.
- Review `main.py` (created by `uv init`) — Django apps run via `manage.py runserver`, so `main.py` is unused and can be deleted.
- Configure Django settings for the `melo-gierka` real-time party music game: the default `SECRET_KEY` in `melo_gierka/settings.py` is dev-only, `DEBUG = True` should be flipped before any deployment, and `ALLOWED_HOSTS` needs the Fly hostname when you stand up the staging environment.
- The audit ran clean against today's vulnerability databases. Re-run `pip-audit` periodically (or wire it into CI) as the dependency tree evolves.
