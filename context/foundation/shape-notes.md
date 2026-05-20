---
project: "MeloGierka"
context_type: greenfield
product_type: web-app
target_scale:
  users: small
  qps: low
  data_volume: small
timeline_budget:
  mvp_weeks: 4
  hard_deadline: 2026-06-30
  after_hours_only: false
created: 2026-05-18
updated: 2026-05-18
checkpoint:
  current_phase: 8
  phases_completed: [1, 2, 3, 4, 5, 6, 7]
  gray_areas_resolved:
    - topic: "pain category"
      decision: "Coordination overhead w trybie zespołowym offline — pasywni członkowie drużyn się nudzą."
    - topic: "insight"
      decision: "Równoczesna, indywidualna rozgrywka na własnych telefonach + niski próg wejścia (bez logowania) + dobór zakresu czasowego."
    - topic: "primary persona scope"
      decision: "Gospodarz imprezy jako konfigurujący; gracze jako równoprawni uczestnicy sesji."
    - topic: "join mechanism"
      decision: "Link sesji ORAZ kod QR — oba sposoby do wyboru przez gospodarza/graczy."
    - topic: "role split"
      decision: "Gospodarz konfiguruje (zakres czasowy, tryb, start/stop); gracze tylko grają."
    - topic: "disconnect & rejoin"
      decision: "Tożsamość = (imię + kod sesji). Punkty zachowane przy powrocie. Akceptowane ryzyko podszycia się pod znajomego — kontekst zaufanej grupy. UWAGA: powrót po rozłączeniu wypadł z v0 podczas Fazy 3 (scope-down) — wraca w v1."
    - topic: "MVP scope (Faza 3)"
      decision: "Wersja B: Spotify zostaje (5 hardcoded playlist, host wybiera 1); tylko tryb 'zgadnij artystę'; stała liczba 10 rund; polling 1s zamiast WebSocket; bez QR; bez powrotu po rozłączeniu w v0."
    - topic: "primary success criterion"
      decision: "Jedna sesja 4–6 znajomych od początku do końca bez awarii."
    - topic: "guardrails"
      decision: "Lag pokazania pytania ≤ 1s; cichy refresh tokenu Spotify; imiona graczy nie wyciekają poza sesję."
    - topic: "round duration"
      decision: "Fragment 30s = okno na odpowiedź 30s, niekonfigurowalne. Klik tylko podczas grania; po końcu fragmentu runda zamyka się automatycznie."
    - topic: "distractor pool"
      decision: "3 błędne opcje artystów losowane z TEJ SAMEJ playlisty co poprawny — utrudnia (ta sama epoka/gatunek)."
    - topic: "scoreboard granularity"
      decision: "FR-012 (scoreboard po każdej rundzie) zdemotowany do nice-to-have. W v0 tylko ekran wyników końcowych po 10 rundach."
  frs_drafted: 14
  quality_check_status: accepted
---

## Vision & Problem Statement

Gry muzyczne na imprezach grane są zazwyczaj w formacie drużynowym offline. W liczniejszych drużynach część członków nie zdąża się wypowiedzieć — stają się pasywni i zaczynają się nudzić. Gospodarz imprezy chce zaproponować znajomym aktywność muzyczną, w której każdy uczestniczy w **takim samym stopniu**, niezależnie od śmiałości czy refleksu w mówieniu.

Insight: rozgrywka indywidualna na własnym telefonie — bez logowania, bez rozgłosu, z zakresem muzycznym dobranym do publiczności — pozwala wszystkim grać równocześnie i sprawiedliwie. To eliminuje koszt koordynacji drużynowej (kto mówi, kto liczy punkty) i włącza w grę osoby, które w trybie offline zostają w tyle.

## User & Persona

**Gospodarz imprezy** — osoba, która urządza spotkanie towarzyskie i chce zaproponować znajomym wspólną aktywność muzyczną. Zakłada sesję na swoim urządzeniu, dobiera ustawienia (zakres czasowy, tryb zgadywania) i zaprasza znajomych do dołączenia. Jego pain point: dobrze się bawi, gdy wszyscy znajomi się angażują — a w trybie offline drużynowym to nie zawsze działa.

### Secondary persona

**Gracz na imprezie** — znajomy gospodarza, dołącza do sesji ze swojego telefonu, podając tylko imię. Doświadczenie ma być natychmiastowe (≤ 10 sekund od linku do pierwszego pytania) i sprawiedliwe (każdy ma taką samą szansę odpowiedzi).

## Access Control

**Brak konta, brak hasła.** Tożsamość gracza w obrębie sesji = `imię` w połączeniu z 4-znakowym kodem sesji, do którego dołącza. Imię musi być unikalne w obrębie pojedynczej sesji (drugi „Adam" dostaje sugestię „Adam 2" lub musi wybrać inne).

**Dwie role:**

- **Gospodarz** — osoba, która tworzy sesję. Loguje się do Spotify (OAuth, wymóg Premium), wybiera 1 z 5 hardcoded playlist, startuje rozgrywkę. Identyfikowany w przeglądarce jako twórca sesji (np. cookie / token w sessionStorage), bez panelu re-akwizycji uprawnień w v0.
- **Gracz** — dołącza do istniejącej sesji wpisując 4-znakowy kod na URL aplikacji. Odpowiada na pytania. Brak panelu konfiguracji.

**Dołączanie (v0):** gospodarz tworzy sesję, dostaje 4-znakowy kod sesji wyświetlony na ekranie. Dyktuje go znajomym ustnie lub wkleja w czacie. Znajomi wchodzą na URL aplikacji i wpisują kod. Link sesji i kod QR — POZA v0 (wracają w v1).

**Powrót po rozłączeniu (v0):** brak rejoinu. Jeśli gracz straci połączenie i dołączy ponownie, pojawia się jako nowy wpis na liście graczy (z 0 punktów). Rejoin z zachowaniem punktów (tożsamość = imię + kod sesji) — POZA v0 (wraca w v1).

**Gospodarz po rozłączeniu (v0):** zamknięcie karty przez gospodarza kończy sesję. W v0 nie ma mechanizmu odzyskiwania uprawnień gospodarza. (Akceptowalne ryzyko dla pierwszej sesji testowej — gospodarz nie zamyka karty przed końcem 10 rund.)

### Forward to v1 (Access Control)

*Decyzje out-of-scope dla v0, zachowane w shape-notes na potrzeby v1 — NIE są częścią PRD v0:*

- Link sesji jako alternatywa kodu (krótki URL np. `/s/ABCD`).
- Kod QR wyświetlany na ekranie gospodarza.
- Rejoin gracza po rozłączeniu — tożsamość przez `(imię, kod sesji)`, punkty zachowane. Trade-off zaakceptowany: można teoretycznie podszyć się pod znajomego, ale w kontekście „impreza wśród znajomych" to akceptowalne ryzyko.
- Token gospodarza w sessionStorage z mechanizmem przywrócenia uprawnień po nieprzewidzianym zamknięciu karty.

## MVP Scope (v0 — what ships in 3–4 weeks)

**W zakresie v0:**

- Gospodarz loguje się do Spotify (wymagane konto **Premium**) i wybiera 1 z **5 hardcoded playlist** zdefiniowanych w aplikacji.
- Sesja zawsze ma **stałą liczbę 10 rund**; brak konfigurowalnej długości.
- Jedyny tryb gry: **„zgadnij artystę"** spośród 4 opcji A/B/C/D.
- Gracze dołączają **wpisując 4-znakowy kod sesji** na URL aplikacji; kod QR i link sesji poza v0.
- Audio leci wyłącznie z **urządzenia gospodarza** (przeglądarka host'a + głośnik imprezowy). Gracze nie odtwarzają niczego u siebie.
- Real-time sync UI przez **HTTP polling co ~1s** (każdy klient pyta serwer o stan rundy).
- **Scoreboard po każdej rundzie** + końcowy ekran wyników po 10 rundach.
- **30 sekund** na rundę (fragment 30s = okno odpowiedzi 30s). Klik tylko podczas grania; po końcu fragmentu runda zamyka się automatycznie. Szybsza poprawna odpowiedź = więcej punktów.
- **Scoreboard tylko końcowy** (po 10 rundach). Scoreboard po każdej rundzie zdemotowany do nice-to-have.

**Poza zakresem v0 (wraca w v1+):**

- Wybór zakresu czasowego / dynamiczna lista playlist Spotify.
- Tryb „autor + tytuł" oraz konfiguracja liczby rund.
- Powrót gracza po rozłączeniu z zachowaniem punktów (rejoinem jako (imię, kod sesji)).
- Kod QR jako alternatywa linku.
- Real-time przez WebSocket / Pusher.

## Success Criteria

### Primary

- Jedna pełna sesja z 4–6 znajomymi (jedna rzeczywista impreza) przebiega **od pierwszego dołączenia do ekranu wyników** bez awarii — nikt nie utknął na błędzie, scoreboard pokazuje poprawne wyniki dla wszystkich graczy.

### Secondary

- Po pierwszej sesji co najmniej jeden gracz pyta „a możemy zagrać jeszcze raz?" — soft sygnał, że gra jest na tyle dobra, by chciało się wracać. *(Propozycja do potwierdzenia przez gospodarza.)*

### Guardrails

- **Lag pokazania pytania ≤ ~1 sekundy** od startu rundy do widoczności na ekranie każdego gracza (polling 1s daje akceptowalny lag przy 4–6 graczach).
- **Pojedyncza sesja v0 nie wymaga refresha tokena Spotify** — sesja trwa ~7 min, token wygasa po 60 min. Guardrail spełniony przez ograniczenie zakresu, nie przez kod. (Refresh tokena — FR-014 nice-to-have — staje się relewantny dopiero przy 2+ sesjach w jednym wieczorze.)
- **Imiona graczy nie wyciekają poza sesję** — brak indeksu w Google, brak publicznej listy sesji, lista graczy widoczna tylko w obrębie własnej sesji.

## Functional Requirements

### Konfiguracja sesji

- FR-001: Gospodarz może zalogować się do Spotify (OAuth, wymóg konta Premium). Priority: must-have
  > Sokrates: Counter-argument considered: „Premium-wall — ~30% użytkowników nie ma Premium, alternatywa to Spotify Free + 30s preview API." Resolution: kept; gospodarz to JEDNA osoba na sesję (osoba organizująca imprezę), bariera Premium akceptowalna; preview API nie wystarcza do gry synchronicznej (brak kontroli nad offsetem fragmentu).
- FR-002: Gospodarz może utworzyć nową sesję i otrzymać **unikalny 4-znakowy kod sesji** do przekazania znajomym ustnie lub w czacie. Priority: must-have
  > Sokrates: Counter-argument considered: „Sam kod bez linku — prostsze do przekazania ustnie na imprezie." Resolution: ZREWIDOWANE — link usunięty, w v0 tylko kod. Niższy koszt UI, lepsza ergonomia imprezowa.
- FR-003: Gospodarz może wybrać 1 z 5 hardcoded playlist Spotify przed startem sesji. Priority: must-have
  > Sokrates: Counter-argument considered: „1 default playlist w v0 — brak wyboru, jeszcze mniej UI, oszczędność ~1 dzień." Resolution: kept; selektor daje gospodarzowi kontrolę nad nastrojem imprezy (zasada z Fazy 1: zakres dobrany do publiczności) — wart 1 dnia pracy.

### Dołączanie i tożsamość

- FR-004: Gracz może dołączyć do sesji przez **wpisanie kodu sesji** w polu na stronie aplikacji (po wejściu na URL aplikacji). Priority: must-have
  > Sokrates: Counter-argument considered: „Długi link Spotify-style jest brzydki" + (rozszerzone) „kod ustnie wystarcza, link nie jest potrzebny." Resolution: ZREWIDOWANE — link usunięty z v0, gracz wchodzi na URL aplikacji i wpisuje 4-znakowy kod (spójne z FR-002).
- FR-005: Gracz może wpisać swoje imię przy dołączaniu — unikalne w obrębie sesji (kolizja → aplikacja sugeruje wariant). Priority: must-have
  > Sokrates: Counter-argument considered: „Pozwól na duplikaty / autonumeruj / generuj pseudonimy." Resolution: kept; walidacja imienia jest tania, scoreboard pozostaje czytelny, gracz świadomie wybiera swoją tożsamość.
- FR-006: Gospodarz może zobaczyć listę dołączonych graczy w czasie rzeczywistym (polling). Priority: must-have
  > Sokrates: Counter-argument considered: „Polling w poczekalni to marnotrawstwo / gospodarz nie musi widzieć listy." Resolution: kept; gospodarz potrzebuje feedbacku „kto już jest", żeby świadomie kliknąć Start. Polling 1s akceptowalny dla 4–6 graczy.

### Rozgrywka

- FR-007: Gospodarz może wystartować sesję, gdy minimum 1 gracz jest dołączony. Priority: must-have
  > Sokrates: Counter-argument considered: „Min 2 graczy / spectator mode dla hosta." Resolution: kept; 1 gracz wystarczy do debug + edge case (gospodarz testuje solo przed imprezą). Atmosfera imprezowa nie wymaga blokady na min 2.
- FR-008: Aplikacja może odtworzyć dokładnie 30s fragment piosenki w przeglądarce gospodarza (Spotify Web Playback SDK) zaczynając od **losowego momentu utworu** (offset wylosowany z zakresu 20–80% długości). Priority: must-have
  > Sokrates: Counter-argument considered: „Intro pierwszych sekund jest zbyt charakterystyczne — gra za łatwa." Resolution: ZREWIDOWANE — fragment startuje z losowego momentu (20–80% długości utworu) zamiast od position_ms=0. Większe wyzwanie, lepszy gameplay. Koszt: 1 linia kodu.
- FR-009: Gracz może zobaczyć 4 opcje artystów (A/B/C/D) na swoim telefonie podczas rundy; 3 dystraktory pochodzą z tej samej playlisty co poprawny. Priority: must-have
  > Sokrates: Counter-argument considered: „3 opcje zamiast 4 / free-text answer." Resolution: kept; 4 to oczekiwany format gier muzycznych (Hitster, SongPop), dystraktory z tej samej playlisty zapewniają sprawiedliwą trudność. Free-text odrzucony (fuzzy matching = duża praca + częste frustrujące „MARKED WRONG").
- FR-010: Gracz może wybrać jedną odpowiedź w trakcie 30s fragmentu; **pierwszy klik blokuje wybór** (brak zmian) i odpowiedź jest natychmiast finalizowana. Priority: must-have
  > Sokrates: Counter-argument considered: „Pozwól zmienić odpowiedź do końca rundy / 2s grace period po fragmencie." Resolution: ZREWIDOWANE — pierwszy klik = lock natychmiast (was: lock na końcu fragmentu). Większa dramaturgia, lepiej współgra z punktacją ważoną czasem.
- FR-011: Aplikacja może przyznać punkty za poprawną odpowiedź ważone czasem odpowiedzi (szybciej = więcej punktów; brak odpowiedzi = 0 punktów). Priority: must-have
  > Sokrates: Counter-argument considered: „Binary scoring / streak bonus." Resolution: kept; ważone czasem to złoty środek między prostotą a dramaturgią; bez streak (over-engineering na pierwszy raz).
- FR-012: Gracz może zobaczyć scoreboard po każdej rundzie (poprawna odpowiedź + bieżące wyniki wszystkich). Priority: nice-to-have
  > Sokrates: Counter-argument considered: „Wytnij całkowicie z v0 / przywróć do must-have." Resolution: pozostaje nice-to-have — pierwsza warto-dodawalna feature po MVP, jeśli czas pozwoli w 4. tygodniu. Bez niej v0 nadal się broni (ekran końcowy wystarcza do pierwszej sesji).

### Zakończenie i niezawodność

- FR-013: Aplikacja może pokazać ekran wyników końcowych po 10 rundach (zwycięzca + ranking wszystkich graczy). Priority: must-have
  > Sokrates: Counter-argument considered: „Wystarczy tekst Game Over / TOP 3 zamiast pełnego rankingu." Resolution: kept; pełny ranking pozwala każdemu zobaczyć swoje miejsce — kluczowe dla satysfakcji „gram, widzę swój wynik". Klasyczny end-game UX.
- FR-014: Aplikacja może cicho odnowić token Spotify gospodarza zanim wygaśnie. Priority: nice-to-have
  > Sokrates: Counter-argument considered: „Sesja v0 = ~7 min, token wygasa po 60 min — refresh niepotrzebny w v0." Resolution: ZDEMOTOWANE do nice-to-have; refresh staje się relewantny tylko gdy gospodarz organizuje 2+ sesje w jednym wieczorze (rzadki przypadek). Pierwsza wersja v0 może to ignorować — gospodarz zaloguje się ponownie przy 2. sesji.

## User Stories

### US-01: Gospodarz organizuje sesję gry muzycznej na imprezie

- **Given** gospodarz ma konto Spotify Premium i znajomych z telefonami w tej samej sieci Wi-Fi
- **When** wchodzi na stronę gry, loguje się do Spotify, tworzy sesję, wybiera playlistę z 5 dostępnych, dyktuje znajomym 4-znakowy kod sesji i klika „Start", gdy wszyscy dołączą
- **Then** sesja startuje: u gospodarza zaczyna grać pierwszy fragment 30s, u każdego gracza na telefonie pojawiają się 4 opcje artystów do wyboru, po 30s runda się zamyka i zaczyna następna; po 10 rundach pokazuje się ekran wyników końcowych ze zwycięzcą

#### Acceptance Criteria

- Wszyscy gracze widzą opcje pytania w czasie ≤ 1s od startu rundy (guardrail polling).
- Jeśli gospodarz przerwie sesję (zamknie kartę), gra przerywa się i nie ma sposobu jej wznowić w v0 (akceptowane).
- Jeśli gracz się rozłączy, ponowne dołączenie w v0 oznacza nowy wpis na liście graczy (z 0 punktów).
- Imię gracza nie pojawia się nigdzie poza interfejsem własnej sesji.

## Business Logic

**Aplikacja generuje sprawiedliwą rozgrywkę muzyczną — losuje fragment utworu z wybranej playlisty, dobiera 3 dystraktory artystów z tej samej playlisty, synchronizuje 4 opcje na wszystkich klientach jednocześnie i przyznaje punkty proporcjonalnie do czasu odpowiedzi.**

**Wejścia (user-facing):** playlista Spotify wybrana przez gospodarza spośród 5 dostępnych; lista graczy w sesji; moment startu kolejnej rundy zainicjowany przez gospodarza.

**Wyjścia (user-facing):** moment startu fragmentu 30s, który wszyscy gracze widzą w tym samym czasie; 4 opcje artystów (1 poprawny + 3 dystraktory z tej samej playlisty) widoczne wszystkim graczom równocześnie; finalna punktacja gracza za rundę, ważona czasem od pokazania opcji do kliknięcia.

**Jak gracz to widzi:** otwiera URL aplikacji → wpisuje 4-znakowy kod sesji → wpisuje imię → czeka aż gospodarz wystartuje grę → słyszy fragment z głośnika gospodarza i widzi 4 opcje na swoim telefonie → klika jedną → widzi czy trafił → przechodzi do następnej rundy. Po 10 rundach: pełen ranking końcowy.

**Co aplikacja decyduje (kluczowe):**
1. **Który utwór z playlisty** — wybór losowy z puli, bez powtórzeń w obrębie jednej sesji.
2. **Od którego momentu odtworzyć fragment 30s** — offset losowy z zakresu 20–80% długości utworu (FR-008).
3. **Które 3 dystraktory pokazać obok poprawnej odpowiedzi** — losowanie z artystów tej samej playlisty (FR-009).
4. **Ile punktów przyznać** — funkcja czasu od pokazania opcji do kliknięcia poprawnej (FR-011).
5. **Kiedy zakończyć sesję** — po 10 rundach (FR-013).

## Non-Functional Requirements

- **Lag pokazania pytania ≤ 1 sekundy** od momentu startu rundy do widoczności 4 opcji u każdego gracza w sesji. Mierzalne na 4–6 graczach.
- **Aplikacja jest używalna** na 2 najnowszych wersjach Chrome, Safari i Firefox na urządzeniach mobilnych (iOS i Android). Gospodarz dodatkowo używa desktopowej przeglądarki obsługującej Spotify Web Playback SDK.
- **Sesja jest ulotna.** Po zakończeniu sesji (ekran wyników końcowych zamknięty / brak aktywności > 1h) nie pozostają w systemach trwałych żadne dane gracza: imiona, scoreboard ani kod sesji. (Privacy by design — wzmocnienie guardrailu z Fazy 3.)

## Non-Goals

- **Brak integracji z innymi serwisami muzyki niż Spotify.** Apple Music, YouTube Music, Tidal, Deezer — wszystkie poza zakresem v0. Multi-provider to gigantyczna praca; v0 lockuje na Spotify.
- **Brak profili graczy, historii wyników i globalnego leaderboardu.** Zgodne z seedem („Możliwość zbierania historii o użytkownikach i tworzenie ich profili" — explicite POZA MVP). Każda sesja jest niezależna, dane nie przeżywają.
- **Brak aplikacji natywnej mobilnej (iOS / Android).** Zgodne z seedem („Aplikacje mobilne — na początek tylko web"). Aplikacja webowa działa w mobilnej przeglądarce — to wystarcza dla v0.
- **Brak czatu / komunikacji między graczami w sesji.** Gracze siedzą obok siebie na imprezie i rozmawiają na żywo; komunikator w aplikacji to zbędne tarcie.
- **Brak monetyzacji.** Brak płatnych playlist, brak reklam, brak Premium tier po stronie aplikacji. Hobby project; monetyzacja zżera czas dewelopera bez wartości dla v0.
- **Brak edytowania playlist przez gospodarza.** Gospodarz nie wkleja URL-i Spotify, nie buduje własnych playlist — tylko wybór z 5 hardcoded. Edytowanie to praca v2+.
- **Brak innych trybów gry niż „zgadnij artystę".** Tryb „artyst + tytuł", „rok wydania", „zanucenie" — wszystkie poza zakresem v0 (mimo że pierwszy z nich jest w pierwotnym seedzie).

## Timeline acknowledgment

`timeline_budget.mvp_weeks: 4` — przekracza domyślne 3 tygodnie skill'a. Acknowledged on 2026-05-18: 4-tygodniowy MVP wymaga sustained effort (~50h pracy wieczornej + okazjonalne bloki dzienne, mix mode); gospodarz świadomie akceptuje koszt. Hard deadline 2026-06-30 daje ~6 tygodni od dziś = bufor ~2 tygodnie na nieprzewidziane zaskoczenia ze Spotify SDK lub real-time sync. Acknowledgment zarejestrowany — skill nie powtarza ostrzeżeń.

## Quality cross-check

Faza 7 uruchomiona 2026-05-18. Status: **accepted** — wszystkie gapy zaadresowane.

| Element | Status | Akcja podjęta |
|---|---|---|
| Access Control | ✓ accepted | Cleanup driftu z v1 → v0; v1 content przeniesiony do `### Forward to v1 (Access Control)` |
| Business Logic (one-sentence rule) | ✓ accepted | Reguła zalockowana w Fazie 5 |
| Project artifacts | ✓ accepted | `shape-notes.md` z poprawnym frontmatter + checkpoint |
| Timeline-cost ack | ✓ accepted | `## Timeline acknowledgment` dodany (4 tyg sustained effort + 2 tyg bufor do deadline 2026-06-30) |
| Non-Goals | ✓ accepted | 7 entries w `## Non-Goals` |

Gapy do mirroratowania w `/10x-prd` → `## Open Questions`: brak.

## Forward: tech-stack

*Dla downstream skilla 10x-tech-stack-selector — informacyjne, nie część PRD:*

- **Wymagana integracja:** Spotify Web Playback SDK + Spotify Web API (OAuth 2.0, scope: streaming + user-read-email).
- **Synchronizacja UI między klientami w sesji** przez HTTP polling (~1s interwał) — bez WebSocket w v0.
- **Mobile-first UX** dla graczy; desktop dla gospodarza (Spotify Web Playback SDK ma ograniczenia mobilne).
- **Sesja ulotna** — w pamięci serwera lub krótkotrwałym storage (Redis-like, TTL ~1h). Brak trwałej bazy graczy/sesji.
- **Hosting:** dowolny, ale musi obsługiwać Spotify OAuth callback URL i HTTPS (wymagane przez Spotify Web Playback SDK).
