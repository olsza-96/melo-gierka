---
change_id: spotify-oauth-scaffold
title: Spotify OAuth scaffold
status: new
created: 2026-06-02
updated: 2026-06-02
archived_at: null
---

## Notes

Lifted from roadmap **F-01** (`@context/foundation/roadmap.md`). GitHub issue: https://github.com/olsza-96/melo-gierka/issues/1.

**Outcome:** host can OAuth-zalogować się do Spotify (scope `streaming` + `user-read-email`), token osadzony w session storage, podstawowy stub odnowy.

**PRD refs:** FR-001, Access Control §Gospodarz (`@context/foundation/prd.md`).

**Unlocks:** S-01 (#5 host-creates-session), S-03 (#7 first-playable-round), S-06 (#10 silent-spotify-token-refresh).

**Live state checked 2026-06-02:**
- Spotify Dev App registered: Client ID `5449c5cfe1de4e09aa789e0a32742eaa`, scopes `streaming` + `user-read-email`.
- Callback URLs whitelistowane: prod `https://melo-gierka.fly.dev/oauth/spotify/callback`, dev `http://127.0.0.1:8000/oauth/spotify/callback`.
- Sekrety wpisane: `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` w Fly secrets (`fly secrets list -a melo-gierka` powinno potwierdzić) oraz w lokalnym `.env` (gitignored).

**Beta-limit ryzyko:** scope `streaming` ma limit ~25 unikalnych userów; dla v0 (4–6 znajomych) wystarczy, ale wymaga Quota Extension Request przy ekspansji.
