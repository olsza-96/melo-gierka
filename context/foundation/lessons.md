# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## Exempt the Fly health-check path from SECURE_SSL_REDIRECT

- **Context**: Django on Fly.io in production. Any deployment whose `fly.toml` ships an `[[http_service.checks]]` block hitting a Django path (`/health` or similar) on `internal_port` over plain HTTP.
- **Problem**: Fly's internal Consul health check hits the machine directly on the private IPv4 over plain HTTP, bypassing the public hostname and the edge proxy. It never sends `X-Forwarded-Proto: https`. With `SECURE_SSL_REDIRECT = True` (the standard prod hardening), Django returns 301 instead of 200; Fly marks the machine unhealthy; the edge proxy then returns 503 to **all** public traffic — even though gunicorn is fine and the app is serving correctly. Diagnostic shape: `fly status` shows machine `started` but `1 check critical`; logs show `"GET /health HTTP/1.1" 301` repeating from `Consul Health Check`.
- **Rule**: When `fly.toml`'s `http_service.checks` hits a Django path on `internal_port`, add `SECURE_REDIRECT_EXEMPT = [r"^health$"]` (with the path name that matches the check) inside the `if not DEBUG:` branch in `settings.py`. Public HTTPS is still enforced by `fly.toml`'s `force_https = true` at the edge — exempting one internal path does not weaken the public surface.
- **Applies to**: implement, impl-review
