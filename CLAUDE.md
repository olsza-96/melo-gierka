# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: melo-gierka

Real-time, multi-player web music-guessing game for parties. Solo project, MVP deadline 2026-06-30.

Canonical product + stack docs (read before designing anything substantive):

- @context/foundation/prd.md — what melo-gierka is, FRs, ACs, success metrics
- @context/foundation/tech-stack.md — chosen stack, deployment, real-time approach

## Stack quirks

- Python 3.10 (`.python-version`); dependencies managed by **uv**, not pip. Use `uv add <pkg>` / `uv sync`; run Django via `uv run python manage.py …`.
- Django 5.2+; project module is `melo_gierka/` (settings = `melo_gierka.settings`). No apps exist yet.
- Real-time is **HTTP polling**, not WebSockets. Do not introduce `channels`, Daphne, or an ASGI realtime server — the tech-stack decision rules them out for v0.
- Deployment target: Fly.io; CI via GitHub Actions (not yet configured).
- Settings are env-driven: `DJANGO_DEBUG` defaults to `False`, and when `DEBUG=False` the `DJANGO_SECRET_KEY` guard refuses to start with the insecure dev sentinel. **For local `manage.py` commands prefix `DJANGO_DEBUG=True`** (e.g. `DJANGO_DEBUG=True uv run python manage.py migrate`). In production, Fly secrets supply the real `DJANGO_SECRET_KEY` / `DJANGO_ALLOWED_HOSTS`.
- Tests: pytest-django via `uv run pytest`. Config in `pyproject.toml` `[tool.pytest.ini_options]`. Use `@pytest.mark.django_db` for DB-touching tests.

## Repo state

- README.md is empty; the PRD is the canonical product description.
- Tests: pytest. No lint, no CI yet.
- `context/archive/` is immutable — never write there.

---

## 10xDevs AI Toolkit — Module 1, Lesson 4

Onboard the agent to the project you scaffolded in Lesson 3 with the **agent-context chain**:

```
(/10x-init  →  /10x-shape  →  /10x-prd  →  /10x-tech-stack-selector  →  /10x-bootstrapper)  →  /10x-agents-md  →  /10x-rule-review  →  /10x-lesson
```

The PRD → tech-stack → bootstrap chain ships from Lessons 1–3 (re-included so you can fix the project mid-flight). `/10x-agents-md`, `/10x-rule-review`, and `/10x-lesson` are the lesson's main topics. The chain extends in Lesson 5 to the infra/deploy step.

### Task Router — Where to start

| Skill | Use it when |
| --- | --- |
| **Agent context (lesson focus)** | |
| `/10x-agents-md` | The repo is scaffolded but the agent has no project-specific onboarding. Inspects the repo (package manifest, README, scripts, lint/test config, layout, commit history) and writes a concise, ordered "Repository Guidelines" to `AGENTS.md` (or, when invoked from a subdirectory, a directory-level `AGENTS.md` reframed around local conventions and the dominant unit). Use as an alternative to the host's built-in `/init` or as a fallback for tools without one. Repo-level body targets ~200 lines; directory-level guides target 120–250 words. |
| `/10x-rule-review <path>` | You have a rules-for-AI file (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*.mdc`, `.github/copilot-instructions.md`, `.windsurfrules`, nested per-area files) and want a 5-axis scorecard: length, embedded code/config snippets, precision of language, redundancy with public knowledge, and rule ordering. Tool-agnostic — scores the artifact's condition, not the project. Default output is read-only; only Check 5 (reorder) may edit, and only with explicit approval. |
| `/10x-lesson [seed]` | You spotted a recurring rule worth surfacing for future runs of `/10x-frame`, `/10x-research`, `/10x-plan`, `/10x-plan-review`, `/10x-implement`, and `/10x-impl-review`. Appends a single entry (Context / Problem / Rule / Applies to) to `context/foundation/lessons.md`. Self-bootstraps the file with the canonical `# Lessons Learned` header on first use. Append-only — never reorders or rewrites prior entries. |
| **Re-run upstream if needed** | |
| `/10x-init` / `/10x-shape` / `/10x-prd` / `/10x-tech-stack-selector` / `/10x-bootstrapper` / `/10x-stack-assess` / `/10x-health-check` | Bundled so you can fix the PRD, swap the stack, or re-scaffold mid-flight. If `/10x-rule-review` flags a `FAIL` you can't shrink your way out of, that often points back to ambiguous PRD or stack decisions — re-run the upstream skill rather than padding `AGENTS.md` with corrections. |

### How the chain hands off

- `/10x-agents-md` writes (or surgically updates) `AGENTS.md` at the resolved scope. Repo-level scope = the file lives at the repo root and frames the project as a whole; directory-level scope = the file lives next to the code it governs and reframes around the local unit, dropping repo-wide framing entirely. The skill never silently overwrites — it switches to an update flow when the target exists.
- `/10x-rule-review` reads any rules-for-AI markdown file you point it at and prints a 5-check scorecard (`OK` / `WARN` / `FAIL`) with concrete fixes. It does not depend on `/10x-agents-md` having run; you can review `.cursor/rules/`, copilot instructions, or a hand-written `CLAUDE.md` the same way.
- `/10x-lesson` self-bootstraps `context/foundation/lessons.md` on first use, then appends one Context/Problem/Rule/Applies-to entry per invocation. The file is consumed as a prior by the planning- and review-phase skills introduced later in the workflow — `/10x-frame`, `/10x-research`, `/10x-plan`, `/10x-plan-review`, `/10x-implement`, `/10x-impl-review`.

### What the lesson's skills capture (and what they do NOT)

- **`/10x-agents-md` captures**: project structure, build/test/lint commands actually present in scripts, commit conventions inferred from history, repo-specific tripwires the agent would otherwise miss, references to canonical files via `@`-paths instead of pasting their content. Directory-level scope additionally captures: local naming/layout patterns inferred from siblings, allowed/forbidden imports, the test pattern used by neighbours, and tripwires visible in the immediate area.
- **`/10x-agents-md` does NOT** paste in the contents of `tsconfig.json` / `eslint.config` / framework docs the agent already knows; it does NOT generate generic "write clean code" intentions; it does NOT replace the host's built-in `/init` when one exists — it's positioned as an alternative or fallback, not a default.
- **`/10x-rule-review` captures**: a length verdict (OK ≤ 200 non-empty lines, WARN 201–500, FAIL 501+), code/config blocks that should be `@`-references instead, vague-intention language, redundancy with framework docs the agent already has from training, and a Check 5 reorder proposal that surfaces critical rules to the top.
- **`/10x-rule-review` does NOT** edit the file by default; it does NOT score project content (architecture, stack choices) — it scores the rule artifact's condition; it does NOT generate a "fixed version" of the file (Check 5 may move sections with explicit approval, never rewrite rule wording).
- **`/10x-lesson` captures**: one entry per invocation with a short imperative H2 title (the title IS the rule), Context (subsystem / phase / file pattern, specific enough to pattern-match), Problem (what concretely breaks without the rule, ideally with a past incident), Rule (1–2 imperative sentences pasteable verbatim into a future review finding), Applies to (subset of `frame`, `research`, `plan`, `plan-review`, `implement`, `impl-review`, or `all`).
- **`/10x-lesson` does NOT** edit or remove existing lessons — the file is append-only by design (rewriting recurring rules without thought is the failure mode this convention prevents); it does NOT batch multiple rules per invocation; it does NOT pre-fill fields proactively (the user does the writing — that's the price of capturing rules outside a structured review).

### The five-pattern calibration drill

Before writing a rule, validate that the agent actually breaks the convention without it. Pick one pattern from your project (error-response shape, file naming, import style, module structure, date handling). Then:

1. Ask the agent to implement against the pattern 3–5 times from a clean state, no rule.
2. Note where it broke the convention; capture run time, files explored, and visible cost/tokens if the host surfaces them.
3. Add a 1–3-sentence rule to the appropriate scope (root or area-level).
4. Re-run the same task in a fresh session and compare convention adherence, time, files, and iterations.

If the agent already trends toward the convention without the rule, you don't need the rule. If it systematically picks the wrong pattern, you've found a high-leverage rule to add. This drill is what "earning a rule from a recurring failure" actually looks like.

### Inner-loop hooks (deterministic feedback without prompting)

Mechanical, non-pickable checks belong in hooks (e.g. Claude Code's `PostToolUse`), not in the rule file. The agent finishes an edit; a formatter or fast lint runs; the result feeds back without you reminding it. Settings template (`settings.json.template`) ships in the lesson pack as the wiring entry point. Keep procedural workflows (deeper review, release checklist, deploy on sandbox) in skills, and reserve hooks for deterministic tool signals.

### Foundation paths used by this lesson

- `AGENTS.md` / `CLAUDE.md` (and per-area variants) — `/10x-agents-md` output
- `context/foundation/lessons.md` — `/10x-lesson` output (append-only register, consumed by future planning/review skills)
- `context/foundation/prd.md`, `context/foundation/tech-stack.md` — inputs from earlier lessons, still present
- `docs/reference/contract-surfaces.md` — load-bearing names registry (scaffolded by `/10x-init`)

<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 3, Lesson 4

Lesson 4 is about **E2E tests** — catching the failures that hooks and unit tests can't see: data that doesn't survive a full user path, broken navigation, a regression that only exists in the rendered UI. An agent can generate a passing E2E test easily; the hard part is making it actually protect a risk and survive tomorrow's refactor. Two quality levers do that work: a **seed test** that shows the agent what a good E2E test looks like, and **rules** that constrain what the agent produces. The prompt only supplies what those two can't encode — the specific risk, flow, and boundaries.

```
context/foundation/test-plan.md  (top 2–3 risks that need browser-level coverage)
        │
        ▼
   seed.spec.ts  +  E2E rules  →  shape every generated test
        │                            (getByRole, isolation, wait-for-state, real vs mocked boundaries)
        ▼
   prompt-template / Planner→Generator  →  test for one risk  →  YOUR review (5 anti-patterns)  →  CI
```

Agents see the **accessibility tree** (roles, names, states in a YAML snapshot with element refs), not pixels — so they should naturally produce `getByRole`-based tests, not CSS selectors. Vision is a supplement for what the DOM can't express (layout, z-index, animation), not the default.

### Task Router — Where to start

| Tool / Prompt | Use it when |
| --- | --- |
| `m3l4-e2e-prompt` prompt | You picked a risk from `test-plan.md` and want one E2E test now. The template forces the E2E contract: risk, research anchor, business scenario (the assertion), real boundaries (don't mock — the risk hides there), mocked boundaries (network layer). Keep it short — the seed test and rules do the heavy lifting; the prompt adds only the risk, flow, and boundaries. |
| Playwright CLI (`@playwright/cli`) | The agent is also editing code and navigating files. CLI runs as shell commands and writes snapshots to disk (~27K tokens/scenario) instead of holding full a11y trees in context (~114K via MCP). Token-frugal default for a coding agent. |
| Playwright MCP (`@playwright/mcp`) | A dedicated browser-automation session (long exploration, scraping, monitoring) where the richer 30+ tool set and in-context session beat token frugality. Add `--caps=vision` only when a risk is visual. |
| Planner→Generator (`npx playwright init-agents`) | You want the agents to explore the app and turn the plan into TypeScript. Still needs a `seed.spec.ts` — the Planner uses it as the example for every generated test, so seed quality is test quality. |
| Healer | An E2E test failed because a **selector** changed (a refactor moved/renamed an element). Healer re-finds it. Route healer output through PR review, never auto-commit. |

### E2E Testing Rules (the key rules)

```
# E2E Testing Rules

- Use getByRole, getByLabel, getByText as primary locators.
  Fall back to getByTestId only when accessibility attributes are ambiguous.
- Never use CSS selectors, XPath, or DOM structure for locating elements.
- Each test must be independently runnable — no shared state between tests.
- Never use page.waitForTimeout(). Wait for specific conditions:
  toBeVisible(), waitForURL(), waitForResponse().
- Assert the business outcome, not implementation details.
- Use unique identifiers (e.g., timestamp suffix) for test data
  to avoid collisions in parallel runs. Clean up in afterEach.
- Use storageState for authentication — never log in through UI
  in individual tests.
```

Additional rules that govern E2E quality:

- **Don't generate E2E tests from scratch.** Start from `test-plan.md`: pick the 2–3 highest risks that need browser-level coverage and feed them as input. A risk needs E2E when it crosses several system boundaries (auth, routing, API, DB) or exists only in the rendered UI; if an isolated function can prove it, a unit test from Lesson 2 is enough.
- **E2E ≠ zero mocking.** Internal boundaries (auth, routing, DB) stay real — that's where integration risk hides. Mock expensive/non-deterministic external APIs (LLMs, payment gateways) at the network layer.
- **Name the test after the risk:** `test('flashcard data persists after page reload', ...)`, not `test('test 1', ...)`.
- **The assertion must fail if the risk materializes.** Control question for every assertion: would this fail if the `test-plan.md` risk came true? If not, it's decorative.

### Five agent E2E anti-patterns — review every generated test against these

1. **Hallucinated assertion** — syntactically valid, semantically empty (asserts the page title instead of that the data survived the reload). Fix: assert the actual business outcome.
2. **Brittle selector** — `page.locator('div.card-container > div:nth-child(3) > button')` instead of `getByRole('button', { name: 'Delete' })`. Breaks on any layout change.
3. **Shared state between tests** — test B assumes test A ran. Playwright runs in parallel, random order → flaky. Each test does its own setup, action, assertion, cleanup.
4. **`waitForTimeout` instead of waiting for state** — passes locally, flakes in CI. Replace with `waitForResponse('**/api/...')` or `expect(locator).toBeVisible()`.
5. **No cleanup** — second run hits a unique-constraint violation. Use unique identifiers (timestamp suffix) plus cleanup per test / `afterEach`.

Re-prompt discipline (same as Lesson 2, lifted to E2E): never say "fix this test". Name the specific anti-pattern, explain why it doesn't protect the risk (or why it produces false failures), and give the target pattern.

### Vision and the healer boundary

- **DOM (snapshot) is the default** for functional verification (does the element exist, did the data save). **Vision** (`--caps=vision`) is a supplement for visual risks only: layout regression, z-index, animation, canvas elements absent from the a11y tree. It costs money and time and can hallucinate — not a default. For pixel-level regression prefer deterministic tools (`toMatchSnapshot`, Argos, Lost Pixel).
- E2E runs in **CI**, not per-edit — a full pass takes minutes. (Hooks from Lesson 3 are the per-edit layer.)
- **Healer helps on selectors, harms on logic.** A changed selector → healer re-finds the element. A changed business behavior (backend returns a new/wrong response) → healer "fixes" the test to match the broken state, masking the bug. That harder case — failing test to root cause to fix — is Lesson 5.

### Lesson boundaries

- This lesson owns E2E: Playwright CLI/MCP, accessibility-tree interaction, seed test + E2E rules, the prompt-template/Planner→Generator flow, vision as a supplement, and test-data isolation.
- Do not configure hooks or local quality layers. That is Lesson 3.
- Do not run the bug-to-fix-to-regression-test debugging workflow. That is Lesson 5 (the healer-on-logic case lives there).
- Do not change the risk strategy or quality-gate definitions. That is Lesson 1 (`/10x-test-plan`).
- Do not write unit/integration test code as the primary deliverable. That is Lesson 2; E2E covers cross-boundary and UI-only risks unit tests can't reach.
- Do not author CI/CD pipelines from scratch. That is Module 1 Lesson 5 / Module 2 Lesson 5; this lesson only says E2E belongs in CI.

### Paths used by this lesson

- `seed.spec.ts` — the exemplar test the Planner copies into every generated test (`getByRole`, isolation, wait-for-state, unique ids + cleanup, risk-named test).
- `playwright.config.ts` — `storageState` for authenticated tests; setup/teardown projects.
- `playwright/.auth/user.json` — saved session state (add the directory to `.gitignore`).
- `context/foundation/test-plan.md` — the checklist of risks that need browser-level coverage; E2E tests trace back to its rows.
- `.claude/prompts/m3l4-e2e-prompt.md` — the E2E generation prompt-template.

<!-- END @przeprogramowani/10x-cli -->
