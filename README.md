# Melo Gierka

Webowa gra muzyczna multiplayer na imprezy, z hostem i graczami dołączającymi kodem sesji.

Projekt jest zbudowany jako MVP w Django i skupia się na:
- tworzeniu sesji przez hosta,
- dołączaniu graczy kodem,
- rundach z odpowiedziami i punktacja zależna od czasu,
- odświeżaniu stanu przez HTTP polling,
- finalnym rankingu po 10 rundach.

## Stack

- Python 3.10
- Django 5.2
- uv do zarządzania zależnościami
- SQLite (lokalnie)
- Spotify OAuth dla hosta
- Sentry (opcjonalnie, przez `SENTRY_DSN`)
- Deploy: Fly.io

## Struktura repo

- `catalog/` – katalog muzyczny, strona główna, endpoint health
- `game/` – logika sesji, lobby hosta/gracza, API rund i odpowiedzi
- `melo_gierka/` – konfiguracja Django (settings, urls, wsgi/asgi)
- `tests/` – testy smoke i E2E
- `context/foundation/` – dokumenty foundation (PRD, roadmapa, tech-stack)

## Wymagania

- Python 3.10 (`.python-version`)
- `uv` zainstalowany globalnie

## Szybki start lokalnie

1. Instalacja zależności:

```bash
uv sync
```

2. Migracje bazy:

```bash
DJANGO_DEBUG=True uv run python manage.py migrate
```

3. Załadowanie przykładowego katalogu muzycznego:

```bash
DJANGO_DEBUG=True uv run python manage.py seed_catalog
```

4. Uruchomienie aplikacji:

```bash
DJANGO_DEBUG=True uv run python manage.py runserver
```

Aplikacja będzie dostępna pod `http://127.0.0.1:8000`.

## Testy

Pełny zestaw testów:

```bash
DJANGO_DEBUG=True uv run pytest
```

Przykłady uruchamiania wybranych testów:

```bash
DJANGO_DEBUG=True uv run pytest game/tests.py -k session_state
DJANGO_DEBUG=True uv run pytest game/tests/test_sentry_command.py -q
```

Testy E2E (Playwright) znajdują się w `tests/e2e/` i wymagają skonfigurowanego środowiska Playwright.

## Zmienne środowiskowe

Najważniejsze zmienne:

- `DJANGO_DEBUG` – lokalnie ustawiaj na `True` dla komend manage.py
- `DJANGO_SECRET_KEY` – wymagany bezpieczny klucz na produkcji
- `DJANGO_ALLOWED_HOSTS` – hosty aplikacji (CSV)
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `SPOTIFY_REDIRECT_URI`
- `SENTRY_DSN` – opcjonalnie, włącza raportowanie do Sentry
- `SENTRY_ENVIRONMENT` – np. `development` lub `production`

Uwaga: przy `DEBUG=False` aplikacja nie wystartuje z domyślnym devowym sekretem.

## Healthcheck

Endpoint health:

```text
GET /health
```

Zwraca:

```json
{"status": "ok"}
```

## Deploy

Deploy produkcyjny jest skonfigurowany na Fly.io:

- workflow GitHub Actions: `.github/workflows/fly-deploy.yml`
- trigger: push do `main`
- wymagany sekret repo: `FLY_API_TOKEN`

## Troubleshooting

### Spotify OAuth – błąd "Redirect URI mismatch"

**Problem**: Podczas logowania przez Spotify pojawia się błąd `redirect_uri_mismatch`.

**Rozwiązanie**:
- Sprawdź, że `SPOTIFY_REDIRECT_URI` w `.env` (lokalnie) lub `fly secrets` (produkcja) pasuje dokładnie do URI zarejestrowanego w [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
- Lokalnie: `http://127.0.0.1:8000/oauth/spotify/callback`
- Na produkcji (Fly.io): `https://melo-gierka.fly.dev/oauth/spotify/callback` (lub Twoja domena)

### Sentry – raporty nie trafiają do projektu

**Problem**: Zdarzenia nie pojawiają się w Sentry dashboard.

**Rozwiązanie**:
- Upewnij się, że `SENTRY_DSN` jest ustawiony (`fly secrets set SENTRY_DSN=...`)
- Sprawdź, czy `SENTRY_ENVIRONMENT` to `production` (domyślnie `development` lokalnie)
- Testuj wysyłkę événu: `uv run python manage.py test_sentry --message "test" --with-exception`
- Patrz sekcję "Sentry" w [CLAUDE.md](CLAUDE.md) dla pełnej konfiguracji

### Deploy na Fly.io – transient failures

**Problem**: Deploy czasem pada z błędem `grpc/EOF` lub timeout.

**Rozwiązanie**:
- Workflow `.github/workflows/fly-deploy.yml` zawiera retry loop (3 próby)
- Jeśli problem się powtarza:
  1. Sprawdź `flyctl logs -a melo-gierka` na Fly dla szczegółów
  2. Upewnij się, że `FLY_API_TOKEN` jest ustawiony w GitHub Secrets
  3. Spróbuj deploy manualnie: `flyctl deploy --remote-only`

### Testy E2E – brak Playwright'a

**Problem**: `ModuleNotFoundError: No module named 'playwright'`

**Rozwiązanie**:
```bash
uv sync  # zainstaluj dev zależności
uv run pytest --playwright-version  # weryfikuj
```

## Dokumentacja produktowa

Kluczowe dokumenty produktu i zakresu:

- `context/foundation/prd.md`
- `context/foundation/roadmap.md`
- `context/foundation/tech-stack.md`
