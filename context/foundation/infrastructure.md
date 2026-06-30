---
project: melo-gierka
researched_at: 2026-05-25
recommended_platform: Fly.io
runner_up: Railway
context_type: mvp
tech_stack:
  language: python
  framework: django
  runtime: python-3.10
  package_manager: uv
---

## Recommendation

**Deploy on Fly.io.**

> **2026-05-25 update**: The `waw` (Warsaw) region was deprecated by Fly.io; new resources cannot be provisioned there. melo-gierka deployed to `ams` (Amsterdam) as the documented fallback. The Polish-low-latency argument below is preserved for historical context but no longer applies — `ams` adds ~30 ms one-way vs `waw`, still well within the ≤1 s polling guardrail.

Fly.io ships a `waw` (Warsaw) region — the lowest-latency match for melo-gierka's Polish party use case — keeps `fly releases rollback` as a first-class CLI command (Railway and Render both deferred rollback to dashboard/REST API), and is the only candidate whose first-class Django path documents the full `gunicorn + whitenoise + secrets + autostop` story. Choosing it preserves continuity with `context/foundation/tech-stack.md`, where Fly.io was named as the deployment target during stack selection. The two real operational tradeoffs — a hand-rolled `Dockerfile` because `fly launch` does not auto-detect `uv`, and the default `auto_stop_machines = "stop"` which collides with the PRD's ≤1 s polling guardrail — are one-time setup items, both with concrete fixes captured below in the risk register.

## Platform Comparison

Hard runtime filter drops three candidates from shortlisting before scoring:

| Platform | Drop reason |
|---|---|
| Netlify | No native Python/Django runtime in 2026; functions are JS/TS/Go only. Netlify support forum explicitly redirects Django users elsewhere. |
| Cloudflare Workers | Python runtime is open beta on Pyodide; Django is not in the supported-framework list. The `django-cf` community package warns it exceeds free-plan CPU limits — forces a rewrite of session/round state onto Durable Objects. |
| Vercel | Python serverless runtime supports Python 3.12+ only; Python 3.10 in `.python-version` is not on the supported list. Cold starts and the 4 hours/month active-CPU budget on Hobby directly threaten the ≤1 s polling guardrail. |

Three shortlisted, scored against the agent-friendly criteria (Pass / Partial / Fail):

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP / Integration |
|---|---|---|---|---|---|
| **Fly.io** | Pass — `flyctl` covers full lifecycle including `releases rollback` | Partial — autostop on by default; `min_machines_running = 1` required to protect ≤1 s guardrail | Pass — every docs page available as Markdown via `/index.md` or `Accept: text/markdown` | Pass — `flyctl` GA and stable; `fly deploy` / `fly secrets` / `fly logs` mature | Partial — `fly mcp` is experimental (per fly.io/docs/flyctl/mcp-server/) |
| **Railway** | Pass — `railway` CLI GA for deploy/logs/env vars | Pass — always-on by default; Serverless opt-in (10-min outbound-idle → sleep, 502 on first request) | Pass — `docs.railway.com/llms.txt` + `llms-full.txt`; any page serves Markdown via `.md` suffix | Partial — rollback is dashboard / REST only (no `railway rollback` subcommand) | Partial — `@railway/mcp-server` is "work in progress" but already supports deploy/logs/env/scale/domains |
| **Render** | Pass — `render` CLI GA since 2024-12-09 | Partial — Free spins down after 15 min (~60 s wake); Starter $7/mo required for always-on | Pass — official `llms.txt` + `llms-full.txt`; `render-oss/skills` GitHub repo for agents | Partial — rollback via REST API + dashboard only (CLI lacks `rollback`) | Partial — MCP server GA (Aug 2025) but **cannot trigger deploys** and cannot modify/delete resources except env vars |

### Shortlisted Platforms

#### 1. Fly.io (Recommended)

Wins on three concrete properties the other two cannot match: a Warsaw region (`waw`), a CLI `releases rollback` that works without leaving the terminal, and the deepest first-class Django reference path of the three (`fly.io/docs/django/`). Cost lands at ~$2–6/mo for a `shared-cpu-1x` always-on machine plus negligible bandwidth at the scale of a handful of parties per month. The Django-on-Fly story is documented end-to-end: WSGI via gunicorn, Whitenoise for statics, `fly secrets` for env vars, `fly logs` for tailing. The two compromises (uv DIY-Dockerfile, default autostop) are written into the risk register with one-line mitigations.

#### 2. Railway

Strong runner-up on three different properties: Railpack auto-detects `pyproject.toml` + `uv.lock` so no Dockerfile is needed; services are always-on by default with Serverless explicitly opt-in (so the ≤1 s guardrail is the default, not something you configure); and the `@railway/mcp-server` integration with Claude Code already supports triggering deploys — a capability Render's GA MCP server explicitly lacks. Loses to Fly.io on region (Amsterdam ~1100 km from Warsaw vs `waw`), on rollback (dashboard-only), and on the agent-driven `flyctl releases rollback` flow that Fly's CLI keeps clean. A reasonable swap target if the uv-Dockerfile friction on Fly.io proves worse than expected in week 1.

#### 3. Render

Third by elimination. Native uv support via `uv.lock` is GA, the `llms.txt` + `llms-full.txt` corpus is the most agent-friendly of the three, and the MCP server is the only one labeled GA. But Render's MCP server **cannot trigger deploys** and cannot modify/delete most resources — a major gap for agent-driven operations. Frankfurt region is acceptable (~950 km from Warsaw), but Starter $7/mo is required from day 1 because the free-tier 15-min spindown + ~60 s cold start violates the PRD's ≤1 s polling guardrail. Stronger pick if you decide later that read-only agent observability is enough and human-driven deploys are fine.

## Anti-Bias Cross-Check: Fly.io

### Devil's Advocate — Weaknesses

1. **uv is not first-class.** `fly launch` auto-detects Python but not uv; the community thread "Deploying Django/Python apps that use uv?" (Apr 2025) confirms users hand-roll Dockerfiles. For a 5-week solo timeline this is yak shaving on week 1.
2. **Free tier removed Oct 2024.** `tech-stack.md` line "free at MeloGierka's scale (hobby tier)" is now inaccurate. A credit card is required from day 1; expect ~$2–6/mo always-on.
3. **Default `fly.toml` has `auto_stop_machines = "stop"` and `min_machines_running = 0`.** If forgotten, the first poll after the host opens a session in the lobby misses the ≤1 s guardrail by a wide margin (machine wake = several seconds).
4. **`fly mcp` is experimental.** Claude-driven `fly logs` / `fly deploy` via MCP is not production-grade; the agent will fall back to shell `flyctl` and lose structured tool-call context.
5. **In-process state dies on every deploy.** Django's default DB-backed sessions need persistent storage; the PRD's "ephemeral session state" only works cleanly with in-memory storage, but a single `fly deploy` mid-game bounces the machine and kills every active room. Either wire Upstash Redis early or accept "deploy = active games lost."

### Pre-Mortem — How This Could Fail

Solo dev ships melo-gierka on Fly.io with default `fly launch` settings. First real party, 25 June 2026: host opens session, dictates the four-character code, four friends join. Round 1 starts — except the machine had autostopped during the 10-minute lobby chat. First poll lands cold; wake takes four seconds. Players see "options not loaded" past the start of the fragment, score zero, and lose the dramaturgy of the first round. Dev didn't read the autostop docs because the Django tutorial doesn't surface them. A week later `min_machines_running = 1` is wired in — works fine, but the demo was cringe. In parallel: 6 hours burned hand-rolling the uv Dockerfile because the Django tutorial assumed `pip` and `uv.lock` kept tripping on missing `.python-version` pin. The experimental `fly mcp` server kept dropping SSE connections, so Claude Code fell back to shell `flyctl`. With one week left until the MVP deadline, dev considers swapping to Railway but the freeze is locked.

### Unknown Unknowns

- **Whitenoise is not auto-wired.** Django serves zero static files until `STATIC_ROOT` + middleware are configured manually. Admin UI broken on first deploy is the classic pitfall.
- **Single-machine deploys cause brief downtime.** `fly deploy` on `shared-cpu-1x` is not zero-downtime; active sessions disconnect for a few seconds during rollout.
- **Default gunicorn worker count does not match RAM allocation.** Four workers on 256 MB RAM will OOM-kill; the rule of thumb is ~1 worker per 256 MB.
- **TLS cert provisioning for custom domains can take 60+ minutes.** Not a problem for `*.fly.dev`, but if you later wire `melo-gierka.party` or similar, plan ahead.
- **`fly mcp server` uses SSE+HTTP transport.** Some corporate proxies / VPNs block SSE; if you run from a restrictive network, MCP gets connection-reset errors without a clear log line.
- **Region awareness in `flyctl`.** `fly machine clone` to a second region requires explicit `--region`; running `flyctl status` does not always show region drift if a machine was created in a different region than `fly.toml` declares.

## Operational Story

How Fly.io operates day-to-day for melo-gierka:

- **Preview deploys**: `fly deploy --app <preview-name>` to a separate app (e.g., `melo-gierka-pr-12`). No native PR-preview integration; use GitHub Actions to provision per-branch apps if/when the workflow grows beyond a single environment.
- **Secrets**: `fly secrets set DJANGO_SECRET_KEY=…` writes to Fly's encrypted vault; values are exposed as env vars to the running machine. Rotation: `fly secrets set KEY=newvalue` (triggers a redeploy). Never commit secrets to `fly.toml`.
- **Rollback**: `fly releases list` shows version IDs; `fly releases rollback <version>` restores in-place. Typical revert time: 30–60 s (one machine restart). Does not roll back DB migrations — handle those manually if any are added later.
- **Approval**: Production `fly deploy` and `fly secrets set` for the primary API token require a human in the loop; `fly logs` and `fly releases list` (read-only) are fine for an agent to run unattended.
- **Logs**: `fly logs` tails the running machine; `fly logs --instance <id>` for a specific machine. For agent-driven log inspection, `fly mcp server` (experimental) exposes log retrieval, but expect to fall back to `flyctl` in scripts.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| First poll after autostop misses ≤1 s guardrail | Devil's advocate / Pre-mortem | H | H | Set `min_machines_running = 1` and `auto_stop_machines = "off"` in `fly.toml` before first session. Add a startup smoke test that hits `/health` after deploy to warm the machine. |
| Hand-rolled `uv` Dockerfile breaks build | Devil's advocate / Research finding | M | M | Use a published reference Dockerfile pattern (`pip install uv && uv sync --frozen --no-dev`); commit `uv.lock`; pin Python via `.python-version`; verify locally with `docker build` before first `fly deploy`. |
| Mid-game `fly deploy` kills active rooms (in-memory state) | Devil's advocate | M | H | Treat MVP as "no deploys during a session." When state moves to Upstash Redis (post-MVP), revisit this. Document in `CLAUDE.md` to not deploy on a party day. |
| Whitenoise not configured → broken admin / static on first deploy | Unknown unknowns | H | L | Add `whitenoise` to dependencies, wire `STATIC_ROOT` and middleware before first deploy; run `collectstatic` in the Dockerfile build step. |
| `fly mcp` SSE connection drops → no agent observability | Devil's advocate | M | L | Use shell-fallback (`flyctl logs`, `flyctl releases`) when MCP is unstable; do not depend on MCP for incident response. |
| Default gunicorn workers OOM-kill on 256 MB | Unknown unknowns | M | M | Pin `gunicorn --workers 2 --threads 4` in the start command; scale RAM to 512 MB if memory pressure shows in `fly logs`. |
| Free-tier-removed surprise → unexpected bill | Devil's advocate | L | L | Set a Fly.io spend alert; review billing after the first test session. ~$2–6/mo expected on `shared-cpu-1x`. |
| Single-machine deploys cause brief disconnects | Unknown unknowns | H | L | Communicate "no deploys during a session" in operational docs; for post-MVP, add a second machine + Fly Proxy rolling deploys. |

## Getting Started

Validated against Django 5.2 + Python 3.10 + uv as locked in `context/foundation/tech-stack.md`:

1. **Install flyctl.** macOS: `brew install flyctl`. Sign in with `fly auth login`.
2. **Hand-write a uv-aware Dockerfile** (do not rely on `fly launch` auto-detection — `fly launch` will emit a `pip`-based Dockerfile that ignores `uv.lock`). Minimum shape: `FROM python:3.10-slim`, install `uv`, `COPY pyproject.toml uv.lock .`, `uv sync --frozen --no-dev`, `COPY . .`, `RUN uv run python manage.py collectstatic --noinput`, `CMD ["uv", "run", "gunicorn", "melo_gierka.wsgi", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:8080"]`.
3. **Run `fly launch --no-deploy` to scaffold `fly.toml`**, then immediately edit it: set `primary_region = "waw"`, `auto_stop_machines = "off"`, `min_machines_running = 1` under `[http_service]`. Verify `internal_port = 8080`.
4. **Wire secrets and deploy.** `fly secrets set DJANGO_SECRET_KEY=…` (generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`). `fly secrets set DJANGO_ALLOWED_HOSTS=<app>.fly.dev`. Then `fly deploy`.
5. **Smoke-test.** `fly status` confirms machine is healthy; `curl https://<app>.fly.dev/` returns 200; `fly logs` shows no Whitenoise or static-file warnings. Bookmark `fly releases list` for rollback flow.

## Out of Scope

The following were not evaluated in this research and are deferred:

- Docker image multi-stage optimization and image-size minimization
- GitHub Actions CI/CD pipeline (auto-deploy-on-merge per `tech-stack.md` to be wired in Lesson 5 / infra setup)
- Multi-region failover, HA, or DR — single `waw` machine is the MVP target
- Background workers / job queues — out of scope per PRD (no async work needed)
- Upstash Redis integration for session state — deferred until post-MVP unless `deploy = lost games` becomes unacceptable during testing
