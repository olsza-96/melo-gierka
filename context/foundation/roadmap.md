---
project: MeloGierka
version: 1
status: draft
created: 2026-06-01
updated: 2026-06-06
prd_version: 1
main_goal: market-feedback
top_blocker: external
---

# Roadmap: MeloGierka

> Wyprowadzona z `context/foundation/prd.md` (v1) + auto-zbadanej baseline kodu z 2026-06-01.
> Edytuj w miejscu; archiwizuj przy supersedzie.
> Pozycje poniżej są w kolejności zależności. Tabela "At a glance" to indeks.

## Vision recap

melo-gierka to indywidualna gra muzyczna na imprezie: każdy znajomy gra na swoim telefonie, gospodarz odtwarza 30-sekundowe fragmenty utworów ze Spotify, a wszyscy zgadują artystę spośród 4 opcji. Pełna sesja to 10 rund; punkty ważone czasem odpowiedzi; żadnych kont ani trwałych danych — sesja zaczyna i kończy się z imprezą. Pełny kontekst: `@context/foundation/prd.md`.

## North star

**S-04: Gospodarz może rozegrać pełną 10-rundową sesję z 1+ graczem od dołączenia do ekranu wyników bez awarii** — to literalne Success Criteria §Primary z PRD i najmniejsza pętla end-to-end, której działanie udowadnia, że produkt da się wynieść na realną imprezę.

> Gwiazda przewodnia tutaj = pierwszy slice, którego zadziałanie udowadnia, że główna hipoteza produktu (równoczesna indywidualna gra na własnych telefonach jest sprawiedliwą zabawą na imprezie) się broni. Plasujemy go możliwie wcześnie, bo cała reszta ma sens dopiero gdy ten działa. Test na realnej imprezie 4–6 znajomych jest weryfikacją post-shipowania S-04, nie osobnym slice'em.

## At a glance

| ID    | Change ID                    | Outcome (user can …)                                                         | Prerequisites      | PRD refs                            | Status   |
| ----- | ---------------------------- | ---------------------------------------------------------------------------- | ------------------ | ----------------------------------- | -------- |
| F-01  | spotify-oauth-scaffold       | (foundation) gospodarz OAuth-loguje się do Spotify ze scope `streaming`       | —                  | FR-001, Access Control §Gospodarz   | implemented |
| F-02  | game-session-models          | (foundation) modele GameSession/Player/Round + cleanup TTL                    | —                  | NFR §Sesja ulotna, FR-002, FR-005   | implemented |
| F-03  | mobile-template-skeleton     | (foundation) base templates + Whitenoise + mobile-first layout                | —                  | NFR §Mobile browsers                | implemented |
| F-04  | session-state-polling        | (foundation) endpoint `/api/sessions/<code>/state` zwraca stan sesji do pollingu | F-02               | NFR §Lag ≤1s, FR-006                | implemented |
| S-01  | host-creates-session         | gospodarz tworzy sesję (login Spotify → wybór zestawu → 4-znakowy kod)       | F-01, F-02, F-03   | FR-001, FR-002, FR-003, US-01       | implemented |
| S-02  | player-joins-lobby           | gracz dołącza kodem + imieniem; gospodarz widzi listę graczy przez polling   | S-01, F-04         | FR-004, FR-005, FR-006, US-01       | implemented |
| S-03  | first-playable-round         | host odtwarza 30s fragment, gracz wybiera spośród 4 opcji, dostaje punkty    | S-02               | FR-007, FR-008, FR-009, FR-010, FR-011, US-01 | implemented |
| S-04  | full-ten-round-session       | pełna sesja 10 rund z ekranem wyników końcowych (NORTH STAR)                  | S-03               | FR-013, US-01, NFR §Lag ≤1s         | implemented |
| S-05  | per-round-scoreboard         | gracz widzi ranking po każdej rundzie (nice-to-have z PRD)                    | S-04               | FR-012                              | implemented |
| S-06  | silent-spotify-token-refresh | gospodarz może zagrać 2+ sesje w jednym wieczorze bez ponownego logowania     | F-01               | FR-014                              | implemented |

## Streams

Pomoc nawigacyjna — grupuje pozycje w ramach wspólnego łańcucha zależności. Kanoniczna kolejność wciąż jest w grafie poniżej; ta tabela to proponowana kolejność czytania równoległych ścieżek.

| Stream | Theme                | Chain                                                            | Note                                                                       |
| ------ | -------------------- | ---------------------------------------------------------------- | -------------------------------------------------------------------------- |
| A      | Core loop            | `F-02` → `F-04` → `S-01` → `S-02` → `S-03` → `S-04`              | Główny kręgosłup; gwiazda przewodnia (S-04) jest na końcu tej ścieżki.     |
| B      | Mobile-first UI      | `F-03`                                                           | Standalone foundation — łączy się ze Stream A przy `S-01`.                 |
| C      | External integration | `F-01` → `S-06`                                                  | F-01 łączy ze Stream A przy `S-01`; S-06 to nice-to-have kończące stream.  |
| D      | Polish               | `S-05`                                                           | Standalone polish slice po S-04 (per-round scoreboard, nice-to-have).      |

## Baseline

Co jest już na miejscu w kodzie według stanu na 2026-06-30 (auto-zbadane + potwierdzone). Foundations poniżej zakładają obecność tych elementów i NIE odbudowują ich.

- **Frontend:** present — komplet widoków hosta i gracza w `game/templates/game/` + wspólny layout (`melo_gierka/templates/base.html`) i assety w `game/static/game/`.
- **Backend / API:** present — endpointy aplikacyjne i API sesji/rund działają (`catalog/urls.py`, `game/urls.py`, `game/api_urls.py`), w tym polling stanu i akcje rundowe.
- **Data:** present — modele `MusicSet`/`Track` (`catalog/models.py`) oraz `GameSession`/`Player`/`Round`/`Answer` (`game/models.py`) z migracjami, fixture katalogu i komendą cleanup sesji.
- **Auth:** present — Spotify OAuth hosta + odświeżanie tokenu i guard ownership sesji; tożsamość gracza wiązana przez session binding (`game/views.py`).
- **Deploy / infra:** present — `fly.toml`, `Dockerfile`, workflow `.github/workflows/fly-deploy.yml` (push do `main`) i ustawienia produkcyjne Django pod Fly.
- **Observability:** present — `/health`, logowanie aplikacji oraz integracja Sentry konfigurowana przez env (`SENTRY_DSN`, `SENTRY_ENVIRONMENT`) z komendą smoke-test.

## Foundations

### F-01: Spotify OAuth scaffold

- **Outcome:** (foundation) gospodarz może zalogować się do Spotify (OAuth 2.0, scope `streaming` + `user-read-email`), token osadzony w session storage, podstawowy stub odnowy.
- **Change ID:** spotify-oauth-scaffold
- **PRD refs:** FR-001, Access Control §Gospodarz
- **Unlocks:** S-01 (utworzenie sesji wymaga tokenu hosta), S-03 (Web Playback SDK w przeglądarce hosta wymaga tokenu), S-06 (refresh token).
- **Prerequisites:** —
- **Parallel with:** F-02, F-03
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Spotify Dev App zarejestrowana 2026-06-01 (Client ID `5449c5cf…`) ze scope `streaming` + `user-read-email`, callback URLs whitelistowane (`https://melo-gierka.fly.dev/oauth/spotify/callback` prod, `http://127.0.0.1:8000/oauth/spotify/callback` dev). Sekrety w Fly secrets + lokalnym `.env`. Pozostałe ryzyko: scope `streaming` ma beta-limit ~25 unikalnych userów — dla v0 (4–6 znajomych) wystarczy; przy ekspansji wymaga Quota Extension Request.
- **Status:** implemented

### F-02: Game session models + ephemeral cleanup

- **Outcome:** (foundation) modele `GameSession` (4-char code, host token ref, music_set FK, status, started_at), `Player` (session, name unique-per-session, score), `Round` (session, track FK, started_at, offset_ms, locked_at) z migracjami; task cleanup usuwa sesje bez aktywności > 1h.
- **Change ID:** game-session-models
- **PRD refs:** NFR §Sesja ulotna, FR-002, FR-005, FR-006, FR-013
- **Unlocks:** F-04 (polling czyta z tych modeli), S-01, S-02, S-03, S-04.
- **Prerequisites:** —
- **Parallel with:** F-01, F-03
- **Blockers:** —
- **Unknowns:**
  - PRD §Open Question #3: ostateczny magazyn (Django DB vs Redis-like z TTL). Owner: user. Block: no (dla v0 Django DB + cron cleanup wystarczy; Redis tylko jeśli mid-game-deploy problem z `infrastructure.md` Risk #3 zacznie boleć).
- **Risk:** Modele standardowe dla Django; ryzyko niskie. Decyzja jednorazowa: czy `Player.score` jest persistowany czy obliczany z `Round` events — wybierze `/10x-plan`.
- **Status:** implemented

### F-03: Mobile-first template skeleton + Whitenoise

- **Outcome:** (foundation) `melo_gierka/templates/base.html` z mobile-first layout (320–768px), Whitenoise zwirepowany (per `context/foundation/infrastructure.md` unknown #1), `STATIC_ROOT` + `collectstatic` w Dockerfile, base CSS reset.
- **Change ID:** mobile-template-skeleton
- **PRD refs:** NFR §Aplikacja używalna na 2 najnowszych wersjach Chrome/Safari/Firefox mobile
- **Unlocks:** S-01 (host screen), S-02 (player join page), S-03 (round UI), S-04 (results screen), S-05 (per-round scoreboard).
- **Prerequisites:** —
- **Parallel with:** F-01, F-02
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Whitenoise misconfiguration łamie admin po deploy (per `infrastructure.md` Risk #4). Mitigacja: lokalny `docker build` + manual sanity check `/static/admin/css/base.css` przed pierwszym push do main.
- **Status:** implemented

### F-04: Session state polling endpoint

- **Outcome:** (foundation) endpoint `GET /api/sessions/<code>/state` zwraca stan sesji w JSON (status sesji, lista graczy, aktualna runda z timingiem) z ETag/cache headers dla idle response; answer options i lock-state zostają odłożone do S-03.
- **Change ID:** session-state-polling
- **PRD refs:** NFR §Lag pokazania pytania ≤1s, FR-006, FR-009
- **Unlocks:** S-02 (lobby polling), S-03 (round state polling), S-04 (round progression polling).
- **Prerequisites:** F-02 (czyta z modeli sesji)
- **Parallel with:** F-01, F-03
- **Blockers:** —
- **Unknowns:**
  - PRD §Open Question #5: zachowanie endpointu gdy klient pozostaje w tyle (>1s lag) — zwracać stale-state czy 503? Owner: user. Block: no (default w F-04: zawsze zwróć aktualny stan, klient sam skipnie rundy gdy lag duży; finalna decyzja na poziomie S-04).
- **Risk:** Polling co 1s przy 4–6 graczach = ~6 req/sec do jednej sesji. Gunicorn 2 workers × 4 threads (per `fly.toml` setup z Dockerfile) bez problemu obsłuży; ryzyko niskie.
- **Status:** implemented

## Slices

### S-01: Gospodarz tworzy sesję

- **Outcome:** gospodarz wchodzi na `/`, klika "Zaloguj się Spotify" → OAuth callback → wybiera 1 z 5 zestawów → dostaje 4-znakowy kod sesji wyświetlony na ekranie do podyktowania znajomym.
- **Change ID:** host-creates-session
- **PRD refs:** FR-001, FR-002, FR-003, US-01
- **Prerequisites:** F-01 (Spotify token), F-02 (GameSession model), F-03 (mobile template — host na desktopie ale layout shared)
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - PRD §Open Question #4: zawartość 5 zestawów (które playlisty Spotify? hardcoded URI). Owner: user. Block: no (slice może shipnąć z placeholderami; finalne playlisty kuratorowane po pierwszej sesji testowej).
  - Czy 4-char kod sesji powinien wykluczać mylące znaki (`I`, `1`, `O`, `0`)? Owner: agent. Block: no.
- **Risk:** Pierwszy slice po F-01 — jakiekolwiek błędy w OAuth scope `streaming` lub callback URL surface'ują się tutaj. Sekwencja zaplanowana zaraz po F-01 żeby skrócić feedback loop.
- **Status:** implemented

### S-02: Gracz dołącza do lobby

- **Outcome:** gracz wchodzi na URL aplikacji, wpisuje 4-znakowy kod, wpisuje imię (walidacja unikalności w obrębie sesji z sugestią wariantu przy kolizji), trafia do lobby; gospodarz widzi listę graczy aktualizowaną ≤1s (polling).
- **Change ID:** player-joins-lobby
- **PRD refs:** FR-004, FR-005, FR-006, US-01, NFR §Lag ≤1s
- **Prerequisites:** S-01 (musi być sesja do której dołączać), F-04 (polling endpoint)
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - Czy lobby ma hard limit liczby graczy (PRD mówi "4–6 znajomych" ale to skala docelowa, nie limit)? Owner: agent. Block: no (default: brak hard limitu w v0; soft warning przy >10).
- **Risk:** Pierwszy load test na F-04 — kilku graczy polling + jeden polling u hosta = ~6 req/sec sumarycznie. Jeśli lag pojawia się tu, fix na poziomie F-04 zanim S-04 dotknie 10 rund.
- **Status:** implemented

### S-03: Pierwsza grywalna runda end-to-end

- **Outcome:** gospodarz klika "Start" (FR-007: wystarczy ≥1 gracz w lobby) → Spotify Web Playback SDK odtwarza 30s fragment z losowym offsetem 20–80% utworu → gracze widzą 4 opcje artystów (1 poprawny + 3 dystraktory z tego samego zestawu) → pierwszy klik blokuje wybór i finalizuje odpowiedź → gracz dostaje punkty ważone czasem od pokazania opcji.
- **Change ID:** first-playable-round
- **PRD refs:** FR-007, FR-008, FR-009, FR-010, FR-011, US-01
- **Prerequisites:** S-02 (lobby z dołączonymi graczami)
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - Czy Spotify Web Playback SDK pozwoli na precyzyjny offset (`seek(track.duration_ms * random.uniform(0.2, 0.8))`)? PRD zakłada że tak (FR-008) ale nie zostało zweryfikowane. Spike wewnątrz `/10x-plan first-playable-round`. Owner: agent. Block: no.
  - Algorytm punktacji ważonej czasem — liniowa, wykładnicza, czy odejmowanie od bazy? PRD §FR-011 mówi tylko "szybciej = więcej; brak odpowiedzi = 0". Owner: user/agent. Block: no.
- **Risk:** Najbardziej ryzykowny slice w roadmapie — całe ryzyko zewnętrznej zależności (`top_blocker=external`) materializuje się tu. Plan powinien zacząć od spike'a na Web Playback SDK z offsetem przed pisaniem reszty pętli rundy.
- **Status:** implemented

### S-04: Pełna 10-rundowa sesja z ekranem wyników (NORTH STAR)

- **Outcome:** po pierwszej rundzie sesja automatycznie przechodzi do kolejnej (bez powtórzeń utworu w obrębie sesji); po 10 rundach pokazuje się ekran wyników końcowych (zwycięzca + pełny ranking wszystkich graczy z punktami).
- **Change ID:** full-ten-round-session
- **PRD refs:** FR-013, US-01, NFR §Lag ≤1s, NFR §Sesja ulotna
- **Prerequisites:** S-03
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - PRD §Open Question #5: zachowanie aplikacji gdy pojedynczy gracz ma lag > 1s — runda kontynuuje czy app czeka? Owner: user. Block: no (default: runda kontynuuje, opóźniony gracz dostaje 0 lub klik late z malymi punktami).
- **Risk:** To jest gwiazda przewodnia. Wszystkie poprzednie slice'y mają sens tylko gdy ten działa end-to-end. Werifikacja na realnej imprezie 4–6 znajomych następuje POST-shipowaniu S-04 (nie jest częścią slice'a) — jeśli wyjdzie regresja na większej skali, otworzy się nowy slice scope'owany pod skalowanie.
- **Status:** implemented

### S-05: Scoreboard po każdej rundzie (nice-to-have)

- **Outcome:** po locku/timeout rundy gracze widzą poprawną odpowiedź + bieżący ranking wszystkich graczy (przed startem następnej rundy).
- **Change ID:** per-round-scoreboard
- **PRD refs:** FR-012 (nice-to-have)
- **Prerequisites:** S-04
- **Parallel with:** S-06
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Czysto UI — modele i state z S-04 wystarczą. Sequencing tu, nie wcześniej: PRD demoteł FR-012 do nice-to-have świadomie, ekran końcowy w S-04 wystarcza na pierwszą sesję.
- **Status:** implemented

### S-06: Cichy refresh tokenu Spotify (nice-to-have)

- **Outcome:** token hosta odnawiany ~5 minut przed wygaśnięciem (60min default Spotify) bez wpływu na trwającą sesję; pozwala gospodarzowi rozegrać 2+ sesje w jednym wieczorze bez ponownego logowania.
- **Change ID:** silent-spotify-token-refresh
- **PRD refs:** FR-014 (nice-to-have)
- **Prerequisites:** F-01
- **Parallel with:** S-04, S-05
- **Blockers:** —
- **Unknowns:**
  - Czy refresh token jest issuowany dla scope `streaming`? Owner: agent (verify w spike). Block: no.
- **Risk:** PRD §FR-014: relewantne dopiero przy 2+ sesjach w jednym wieczorze (rzadki przypadek). Może zostać niezrealizowany w v0 bez wpływu na Success Criteria.
- **Status:** implemented

## Backlog Handoff

| Roadmap ID | Change ID                    | Suggested issue title                                              | Ready for `/10x-plan` | Notes                                                       |
| ---------- | ---------------------------- | ------------------------------------------------------------------ | --------------------- | ----------------------------------------------------------- |
| F-01       | spotify-oauth-scaffold       | Spotify OAuth scaffold (host login, scope streaming)               | no                    | Implemented through the host/session flow; standalone change folder was not the delivery vehicle |
| F-02       | game-session-models          | Game session / player / round models + cleanup TTL                 | no                    | Implemented and impl-reviewed on 2026-06-04                  |
| F-03       | mobile-template-skeleton     | Mobile-first base templates + Whitenoise                           | no                    | Implemented in the live app baseline: base template, shared CSS, Whitenoise, `STATIC_ROOT`, Docker collectstatic |
| F-04       | session-state-polling        | Session state JSON polling endpoint                                | no                    | Implemented and impl-reviewed on 2026-06-04                  |
| S-01       | host-creates-session         | Gospodarz tworzy sesję (login Spotify + wybór zestawu + kod)       | no                    | Implemented and impl-reviewed on 2026-06-04                  |
| S-02       | player-joins-lobby           | Gracz dołącza do lobby + host widzi listę graczy                   | no                    | Implemented and impl-reviewed on 2026-06-05                  |
| S-03       | first-playable-round         | Pierwsza grywalna runda end-to-end (Spotify SDK + scoring)         | no                    | Implemented, deployed, smoked, and impl-reviewed on 2026-06-06 |
| S-04       | full-ten-round-session       | Pełna 10-rundowa sesja + ekran wyników (NORTH STAR)                | no                    | Implemented, deployed to dev, and smoked on 2026-06-07       |
| S-05       | per-round-scoreboard         | Scoreboard po każdej rundzie (FR-012 nice-to-have)                 | no                    | Implemented in round surfaces (`host_round` / `player_round`) with live score rendering from session polling |
| S-06       | silent-spotify-token-refresh | Cichy refresh tokenu Spotify (FR-014 nice-to-have)                 | no                    | Implemented: expired Spotify auth payload refreshes before host flow rendering |

## Open Roadmap Questions

1. **Zawartość 5 zestawów muzycznych** (PRD §Open Q #4) — które playlisty Spotify zostaną hardcoded? FR-003 zakłada 5 ale konkretne URI nie ustalone. Owner: user. Block: S-01 (slice może shipnąć z placeholderami; finalne playlisty kuratorowane po pierwszej sesji testowej, nie blokują kodu).
2. **Magazyn ulotnych danych sesji** (PRD §Open Q #3) — Django DB + cron cleanup czy Redis-like z TTL? Dla v0 Django DB wystarczy; przeskok do Redisa otwiera się dopiero gdy "mid-game deploy = lost games" (per `infrastructure.md` Risk #3) zacznie boleć. Owner: user. Block: roadmap-wide (decyzja wpływa na F-02 i F-04).
3. **Edge case: gracz z lagiem > 1s** (PRD §Open Q #5) — runda kontynuuje normalnie u pozostałych, czy aplikacja czeka / pokazuje komunikat? Owner: user. By: przed pierwszą sesją testową. Block: S-04 (default w F-04: zawsze zwróć aktualny stan).

> **Rozwiązane 2026-06-01:** Spotify Developer App registration (`top_blocker=external` zaadresowane). Dev App utworzona ze scope `streaming` + `user-read-email`, callback URLs whitelistowane, Client ID + Secret w Fly secrets i lokalnym `.env`. F-01 przeszło z `blocked` → `ready`.

## Parked

- **Integracja z innymi platformami streamingowymi (Apple Music, YouTube Music, Tidal, Deezer)** — PRD §Non-Goals. v0 lockuje na Spotify; multi-provider to gigantyczna praca.
- **Profile graczy, historia wyników, globalny ranking** — PRD §Non-Goals. Każda sesja niezależna, dane gracza nie przeżywają.
- **Aplikacja natywna mobilna (iOS/Android)** — PRD §Non-Goals. Web mobilne wystarczy w v0.
- **Czat / komunikacja między graczami w sesji** — PRD §Non-Goals. Gracze siedzą obok siebie na imprezie.
- **Monetyzacja** — PRD §Non-Goals. Hobby project.
- **Edytowanie zestawów muzycznych przez gospodarza** — PRD §Non-Goals. v2+ feature.
- **Inne tryby gry (artysta + tytuł, rok wydania, zanucenie)** — PRD §Non-Goals. v2+ feature.
- **WebSocket / Pusher zamiast polling** — shape-notes §Forward to v1. v0 testuje hipotezę że polling 1s wystarczy; jeśli S-04 pokaże regresję, otwiera się nowy slice.
- **Link sesji + QR code jako alternatywa kodu** — shape-notes §Forward to v1. v0 tylko 4-char kod (FR-002).
- **Rejoin gracza po rozłączeniu z zachowaniem punktów** — shape-notes §Forward to v1. v0: nowy wpis z 0 punktów (US-01 §AC).

## Done

- 2026-06-30: `S-05 per-round-scoreboard` uznany za zrealizowany i zsynchronizowany ze stanem kodu.
- 2026-06-30: `S-06 silent-spotify-token-refresh` uznany za zrealizowany i zsynchronizowany ze stanem kodu.
