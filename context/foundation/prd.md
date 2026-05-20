---
project: "MeloGierka"
version: 1
status: draft
created: 2026-05-18
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
---

## Vision & Problem Statement

Gry muzyczne na imprezach grane są zazwyczaj w formacie drużynowym offline. W liczniejszych drużynach część członków nie zdąża się wypowiedzieć — stają się pasywni i zaczynają się nudzić. Gospodarz imprezy chce zaproponować znajomym aktywność muzyczną, w której każdy uczestniczy w **takim samym stopniu**, niezależnie od śmiałości czy refleksu w mówieniu.

Insight: rozgrywka indywidualna na własnym telefonie — bez logowania, bez rozgłosu, z zakresem muzycznym dobranym do publiczności — pozwala wszystkim grać równocześnie i sprawiedliwie. Eliminuje koszt koordynacji drużynowej (kto mówi, kto liczy punkty) i włącza w grę osoby, które w trybie offline zostają w tyle.

## User & Persona

**Gospodarz imprezy** — osoba, która urządza spotkanie towarzyskie i chce zaproponować znajomym wspólną aktywność muzyczną. Zakłada sesję na swoim urządzeniu, dobiera ustawienia (zakres muzyczny, tryb zgadywania) i zaprasza znajomych do dołączenia. Pain point: dobrze się bawi, gdy wszyscy znajomi się angażują — a w trybie offline drużynowym to nie zawsze działa.

### Secondary persona

**Gracz na imprezie** — znajomy gospodarza, dołącza do sesji ze swojego telefonu, podając tylko imię. Doświadczenie ma być natychmiastowe (≤ 10 sekund od otwarcia adresu aplikacji do pierwszego pytania) i sprawiedliwe (każdy ma taką samą szansę odpowiedzi).

## Success Criteria

### Primary

- Jedna pełna sesja z 4–6 znajomymi (jedna rzeczywista impreza) przebiega **od pierwszego dołączenia do ekranu wyników** bez awarii — nikt nie utknął na błędzie, ranking pokazuje poprawne wyniki dla wszystkich graczy.

### Secondary

- Po pierwszej sesji co najmniej jeden gracz pyta „a możemy zagrać jeszcze raz?" — miękki sygnał, że gra jest na tyle dobra, by chciało się wracać.

### Guardrails

- **Lag pokazania pytania ≤ 1 sekundy** od startu rundy do widoczności na ekranie każdego gracza, mierzalne na 4–6 graczach.
- **Gospodarz pozostaje zalogowany na platformie muzycznej przez całą pojedynczą sesję** — dostęp do katalogu nie wygasa w trakcie 10 rund.
- **Imiona graczy nie wyciekają poza sesję** — brak indeksu w wyszukiwarkach, brak publicznej listy sesji, lista graczy widoczna tylko w obrębie własnej sesji.

## User Stories

### US-01: Gospodarz organizuje sesję gry muzycznej na imprezie

- **Given** gospodarz ma aktywną subskrypcję na platformie streamingowej z katalogiem muzycznym oraz znajomych z telefonami w tej samej sieci Wi-Fi
- **When** wchodzi na stronę gry, loguje się na platformie muzycznej, tworzy sesję, wybiera zestaw muzyczny z 5 dostępnych, dyktuje znajomym 4-znakowy kod sesji i klika „Start", gdy wszyscy dołączą
- **Then** sesja startuje: u gospodarza zaczyna grać pierwszy 30-sekundowy fragment, u każdego gracza na telefonie pojawiają się 4 opcje artystów do wyboru, po 30 sekundach runda się zamyka i zaczyna następna; po 10 rundach pokazuje się ekran wyników końcowych ze zwycięzcą

#### Acceptance Criteria

- Wszyscy gracze widzą opcje pytania w czasie ≤ 1 sekundy od startu rundy.
- Jeśli gospodarz przerwie sesję (zamknie kartę przeglądarki), gra przerywa się i nie ma sposobu jej wznowić w v0 (akceptowane).
- Jeśli gracz się rozłączy, ponowne dołączenie w v0 oznacza nowy wpis na liście graczy (z 0 punktów).
- Imię gracza nie pojawia się nigdzie poza interfejsem własnej sesji.

## Functional Requirements

### Konfiguracja sesji

- FR-001: Gospodarz może zalogować się na platformie streamingowej dostarczającej katalog muzyczny (wymagana subskrypcja umożliwiająca odtwarzanie pełnych utworów). Priority: must-have
  > Sokrates: Counter-argument considered: „Wymaganie aktywnej, płatnej subskrypcji odcina część potencjalnych gospodarzy; alternatywą mogłyby być publicznie dostępne 30-sekundowe podglądy utworów." Resolution: kept; gospodarz to jedna osoba na sesję (osoba organizująca imprezę), bariera subskrypcyjna akceptowalna; podglądy nie wystarczają do gry synchronicznej (brak kontroli nad odtwarzanym fragmentem).
- FR-002: Gospodarz może utworzyć nową sesję i otrzymać unikalny 4-znakowy kod sesji do przekazania znajomym ustnie lub w wiadomości tekstowej. Priority: must-have
  > Sokrates: Counter-argument considered: „Sam kod bez linku — prostsze do przekazania ustnie na imprezie." Resolution: ZREWIDOWANE — link sesji usunięty z v0, tylko kod. Niższy koszt UI, lepsza ergonomia imprezowa.
- FR-003: Gospodarz może wybrać 1 z 5 predefiniowanych zestawów muzycznych przed startem sesji. Priority: must-have
  > Sokrates: Counter-argument considered: „1 domyślny zestaw w v0 — brak wyboru, mniej UI, oszczędność ~1 dnia pracy." Resolution: kept; selektor daje gospodarzowi kontrolę nad nastrojem imprezy (zakres muzyczny dobrany do publiczności) — wart dodatkowego ekranu.

### Dołączanie i tożsamość

- FR-004: Gracz może dołączyć do sesji przez wpisanie 4-znakowego kodu sesji w polu na stronie aplikacji. Priority: must-have
  > Sokrates: Counter-argument considered: „Brak linku sesji jako alternatywy — niektórym łatwiej kliknąć link." Resolution: ZREWIDOWANE — w v0 tylko kod (spójne z FR-002). Gracz wchodzi na URL aplikacji i wpisuje 4-znakowy kod. Link wraca w v1.
- FR-005: Gracz może wpisać swoje imię przy dołączaniu — unikalne w obrębie sesji (kolizja → aplikacja sugeruje wariant). Priority: must-have
  > Sokrates: Counter-argument considered: „Pozwól na duplikaty / autonumeruj / generuj pseudonimy." Resolution: kept; walidacja imienia jest tania, ranking pozostaje czytelny, gracz świadomie wybiera swoją tożsamość.
- FR-006: Gospodarz może zobaczyć listę dołączonych graczy aktualizowaną w czasie zbliżonym do rzeczywistego (lag ≤ 1 sekundy). Priority: must-have
  > Sokrates: Counter-argument considered: „Aktualizacja listy w poczekalni to marnotrawstwo / gospodarz nie musi widzieć listy." Resolution: kept; gospodarz potrzebuje feedbacku „kto już jest", żeby świadomie kliknąć Start. Lag ≤ 1s akceptowalny dla 4–6 graczy.

### Rozgrywka

- FR-007: Gospodarz może wystartować sesję, gdy minimum 1 gracz jest dołączony. Priority: must-have
  > Sokrates: Counter-argument considered: „Min 2 graczy / tryb obserwatora dla gospodarza." Resolution: kept; 1 gracz wystarczy do debug + edge case (gospodarz testuje solo przed imprezą). Atmosfera imprezowa nie wymaga blokady na min 2.
- FR-008: Aplikacja może odtworzyć dokładnie 30-sekundowy fragment piosenki na urządzeniu gospodarza, zaczynając od losowego momentu utworu (offset wylosowany z zakresu 20–80% długości). Priority: must-have
  > Sokrates: Counter-argument considered: „Intro pierwszych sekund jest zbyt charakterystyczne — gra za łatwa." Resolution: ZREWIDOWANE — fragment startuje z losowego momentu (20–80% długości utworu) zamiast od początku. Większe wyzwanie, lepszy gameplay.
- FR-009: Gracz może zobaczyć 4 opcje artystów (A/B/C/D) na swoim telefonie podczas rundy; 3 dystraktory pochodzą z tego samego zestawu muzycznego co poprawny artysta. Priority: must-have
  > Sokrates: Counter-argument considered: „3 opcje zamiast 4 / odpowiedź jako wolny tekst." Resolution: kept; 4 to oczekiwany format gier muzycznych, dystraktory z tego samego zestawu zapewniają sprawiedliwą trudność. Wolny tekst odrzucony (rozpoznawanie wariantów nazw to duża praca + częste frustrujące „MARKED WRONG").
- FR-010: Gracz może wybrać jedną odpowiedź w trakcie 30-sekundowego fragmentu; pierwszy klik blokuje wybór (brak zmian) i odpowiedź jest natychmiast finalizowana. Priority: must-have
  > Sokrates: Counter-argument considered: „Pozwól zmienić odpowiedź do końca rundy / 2-sekundowy grace period po fragmencie." Resolution: ZREWIDOWANE — pierwszy klik = lock natychmiast. Większa dramaturgia, lepiej współgra z punktacją ważoną czasem.
- FR-011: Aplikacja może przyznać punkty za poprawną odpowiedź ważone czasem odpowiedzi (szybciej = więcej punktów; brak odpowiedzi = 0 punktów). Priority: must-have
  > Sokrates: Counter-argument considered: „Binary scoring (1 lub 0) / streak bonus za serię trafień." Resolution: kept; ważone czasem to złoty środek między prostotą a dramaturgią; bez streak (over-engineering na pierwszy raz).
- FR-012: Gracz może zobaczyć ranking po każdej rundzie (poprawna odpowiedź + bieżące wyniki wszystkich). Priority: nice-to-have
  > Sokrates: Counter-argument considered: „Wytnij całkowicie z v0 / przywróć do must-have." Resolution: pozostaje nice-to-have — pierwsza warto-dodawalna feature po MVP, jeśli czas pozwoli w 4. tygodniu. Bez niej v0 nadal się broni (ekran końcowy wystarcza).

### Zakończenie i niezawodność

- FR-013: Aplikacja może pokazać ekran wyników końcowych po 10 rundach (zwycięzca + ranking wszystkich graczy). Priority: must-have
  > Sokrates: Counter-argument considered: „Wystarczy tekst Game Over / TOP 3 zamiast pełnego rankingu." Resolution: kept; pełny ranking pozwala każdemu zobaczyć swoje miejsce — kluczowe dla satysfakcji „gram, widzę swój wynik".
- FR-014: Aplikacja może przedłużyć dostęp gospodarza do platformy muzycznej zanim wygaśnie, bez przerwania trwającej rozgrywki. Priority: nice-to-have
  > Sokrates: Counter-argument considered: „Sesja v0 trwa ~7 min — dostęp nie zdąży wygasnąć w trakcie pojedynczej sesji." Resolution: ZDEMOTOWANE do nice-to-have; staje się relewantne dopiero przy 2+ sesjach w jednym wieczorze (rzadki przypadek).

## Non-Functional Requirements

- **Lag pokazania pytania ≤ 1 sekundy** od momentu startu rundy do widoczności 4 opcji u każdego gracza w sesji. Mierzalne na 4–6 graczach.
- **Aplikacja jest używalna** na 2 najnowszych wersjach Chrome, Safari i Firefox na urządzeniach mobilnych (iOS i Android). Gospodarz dodatkowo używa przeglądarki na urządzeniu stacjonarnym lub laptopie do odtwarzania muzyki.
- **Sesja jest ulotna.** Po zakończeniu sesji (zamknięty ekran wyników końcowych / brak aktywności > 1h) nie pozostają w systemach trwałych żadne dane gracza: imiona, ranking ani kod sesji.

## Business Logic

**Aplikacja generuje sprawiedliwą rozgrywkę muzyczną — losuje fragment utworu z wybranego zestawu muzycznego, dobiera 3 dystraktory artystów z tego samego zestawu, prezentuje 4 opcje wszystkim graczom równocześnie i przyznaje punkty proporcjonalnie do czasu odpowiedzi.**

**Wejścia (user-facing):** zestaw muzyczny wybrany przez gospodarza spośród 5 dostępnych; lista graczy w sesji; moment startu kolejnej rundy zainicjowany przez gospodarza.

**Wyjścia (user-facing):** moment startu 30-sekundowego fragmentu, który wszyscy gracze widzą w tym samym czasie; 4 opcje artystów (1 poprawny + 3 dystraktory z tego samego zestawu) widoczne wszystkim graczom równocześnie; finalna punktacja gracza za rundę, ważona czasem od pokazania opcji do kliknięcia.

**Jak gracz to widzi:** otwiera URL aplikacji → wpisuje 4-znakowy kod sesji → wpisuje imię → czeka aż gospodarz wystartuje grę → słyszy fragment z głośnika gospodarza i widzi 4 opcje na swoim telefonie → klika jedną → widzi czy trafił → przechodzi do następnej rundy. Po 10 rundach: pełen ranking końcowy.

**Co aplikacja decyduje (kluczowe dla domeny):**

1. **Który utwór z zestawu** — wybór losowy z puli, bez powtórzeń w obrębie jednej sesji.
2. **Od którego momentu odtworzyć 30-sekundowy fragment** — offset losowy z zakresu 20–80% długości utworu (FR-008).
3. **Które 3 dystraktory pokazać obok poprawnej odpowiedzi** — losowanie z artystów tego samego zestawu (FR-009).
4. **Ile punktów przyznać** — funkcja czasu od pokazania opcji do kliknięcia poprawnej (FR-011).
5. **Kiedy zakończyć sesję** — po 10 rundach (FR-013).

## Access Control

**Brak konta, brak hasła w obrębie aplikacji.** Tożsamość gracza w obrębie sesji = imię w połączeniu z 4-znakowym kodem sesji, do którego dołącza. Imię musi być unikalne w obrębie pojedynczej sesji (drugi „Adam" dostaje sugestię „Adam 2" lub musi wybrać inne).

**Dwie role:**

- **Gospodarz** — osoba, która tworzy sesję. Loguje się na zewnętrznej platformie muzycznej dostarczającej katalog (wymagana aktywna subskrypcja), wybiera 1 z 5 predefiniowanych zestawów, startuje rozgrywkę. W v0 brak panelu odzyskiwania uprawnień gospodarza.
- **Gracz** — dołącza do istniejącej sesji wpisując 4-znakowy kod na URL aplikacji. Odpowiada na pytania. Brak panelu konfiguracji.

**Dołączanie (v0):** gospodarz tworzy sesję, dostaje 4-znakowy kod sesji wyświetlony na ekranie. Dyktuje go znajomym ustnie lub wkleja w wiadomości tekstowej. Znajomi wchodzą na URL aplikacji i wpisują kod.

**Powrót po rozłączeniu (v0):** brak. Jeśli gracz straci połączenie i dołączy ponownie, pojawia się jako nowy wpis na liście graczy (z 0 punktów). Rejoin z zachowaniem punktów — poza zakresem v0.

**Gospodarz po rozłączeniu (v0):** zamknięcie karty przeglądarki przez gospodarza kończy sesję. W v0 brak mechanizmu odzyskiwania uprawnień gospodarza. Akceptowalne ryzyko dla pierwszej sesji testowej.

## Non-Goals

- **Brak integracji z więcej niż jedną platformą streamingową w v0.** Multi-provider to gigantyczna praca; v0 lockuje na pojedynczego dostawcę katalogu muzycznego (wybór konkretnej platformy — patrz Open Questions).
- **Brak profili graczy, historii wyników i globalnego rankingu.** Każda sesja jest niezależna, dane gracza nie przeżywają poza pojedynczą sesją.
- **Brak aplikacji natywnej mobilnej (iOS / Android).** Aplikacja webowa działa w mobilnej przeglądarce — to wystarcza dla v0.
- **Brak czatu / komunikacji między graczami w sesji.** Gracze siedzą obok siebie na imprezie i rozmawiają na żywo; komunikator w aplikacji to zbędne tarcie.
- **Brak monetyzacji.** Brak płatnych zestawów, brak reklam, brak płatnych funkcji po stronie aplikacji. Hobby project; monetyzacja zżera czas dewelopera bez wartości dla v0.
- **Brak edytowania zestawów muzycznych przez gospodarza.** Gospodarz nie buduje własnych zestawów — tylko wybór z 5 predefiniowanych. Edycja to praca v2+.
- **Brak innych trybów gry niż „zgadnij artystę".** Tryb „artysta + tytuł", „rok wydania", „zanucenie" — wszystkie poza zakresem v0.

## Open Questions

1. **Wybór konkretnej platformy streamingowej dostarczającej katalog muzyczny + specyfikacja integracji** — autentykacja, odtwarzanie 30-sekundowych fragmentów z dowolnego momentu utworu, dostęp do metadanych artystów dla wyboru dystraktorów. Notatki z `/10x-shape` wskazują preferowanego dostawcę; finalna decyzja i implementacja w `10x-tech-stack-selector`. Owner: user. By: przed startem implementacji.
2. **Mechanizm synchronizacji UI między klientami w sesji** — utrzymanie lag ≤ 1 sekundy dla 4–6 graczych przy starcie rundy oraz aktualizacji listy graczy. Notatki z `/10x-shape` wskazują preferowany mechanizm; konkretne rozwiązanie w `10x-tech-stack-selector`. Owner: user. By: przed startem implementacji.
3. **Technologia przechowywania ulotnych danych sesji** — sesja żyje ~7 minut + bufor; po godzinie nieaktywności wszystkie dane (imiona graczy, ranking, kod sesji) mają zniknąć z systemów trwałych. Konkretny magazyn w `10x-tech-stack-selector`. Owner: user. By: przed startem implementacji.
4. **Zawartość 5 predefiniowanych zestawów muzycznych** — jakie konkretne playlisty / okresy / gatunki będą hardcoded? FR-003 zakłada 5 zestawów, ale ich zawartość nie jest jeszcze ustalona — kuratorska lista wymaga decyzji. Owner: user. By: przed implementacją FR-003.
5. **Reakcja aplikacji, gdy pojedynczy gracz przekracza guardrail lagu (> 1s)** — czy runda kontynuuje normalnie u pozostałych graczy, czy aplikacja czeka / pokazuje komunikat „twoje połączenie jest wolne"? Edge case do doprecyzowania przed pierwszą sesją testową. Owner: user. By: przed pierwszą sesją testową.
