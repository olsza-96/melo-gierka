---
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
---

## Why this stack

Solo developer building a real-time party music game in 4 weeks, targeting kilkanaście znajomych as the user base. Standard path — Django is the recommended default for `(web, python)` and clears all four agent-friendly gates within the Python training corpus. The product needs a server that handles ephemeral session state (10-round game lifecycle, ~7 min), a polling endpoint sustaining ≤ 1s UI sync between host and players, and a simple mobile HTML join page — Django's batteries-included posture (templates, session middleware, JSON responses) covers all three without external libraries. Real-time is needed (`has_realtime: true`) but implemented as HTTP polling, not WebSockets, which Django handles cleanly in its synchronous model. The streaming audio layer is JS-only in the host's browser and orthogonal to backend language. Fly.io is Django's first deployment default and free at MeloGierka's scale (hobby tier). CI on GitHub Actions with auto-deploy-on-merge — what the starter ships with. The ORM, admin, and migrations Django bundles are unused for ephemeral sessions; that bloat is the accepted cost for staying on the framework's verified path.
