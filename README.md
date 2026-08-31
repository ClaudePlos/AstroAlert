# 🔭 AstroAlert

## ▶ Portal działa pod adresem: **https://claudeplos.github.io/AstroAlert/**

Portal o tym, **co ciekawego dzieje się w kosmosie** – kalendarz zjawisk na niebie
i wydarzeń kosmicznych, który sam się aktualizuje raz na dobę i hostuje się na
GitHub Pages. Zero serwera, zero bazy danych, zero kosztów.

| | |
|---|---|
| **Portal** | https://claudeplos.github.io/AstroAlert/ |
| **English version** | https://claudeplos.github.io/AstroAlert/?lang=en |
| **Kanał RSS** | [polski](https://claudeplos.github.io/AstroAlert/feed.xml) · [English](https://claudeplos.github.io/AstroAlert/feed.en.xml) |
| **Dane** | [`data/events.json`](data/events.json) – otwarte, do użycia w innych projektach |
| **Podgląd lokalny** | `python3 -m http.server 8000` → http://localhost:8000 |

Jeśli pracujesz na własnym forku, Twój adres to
`https://<twoja-nazwa>.github.io/<nazwa-repo>/` – pojawi się po wykonaniu kroków
z sekcji [Uruchomienie u siebie](#uruchomienie-u-siebie).

## Co się dzieje raz dziennie

Codziennie o **04:20 UTC** (06:20 czasu polskiego latem) workflow
[`daily-update.yml`](.github/workflows/daily-update.yml):

1. uruchamia testy,
2. odpytuje źródła i przelicza efemerydy na 400 dni do przodu,
3. scala wynik z poprzednim stanem – **nowe wpisy dostają datę dodania**, a starty
   rakiet, którym przesunięto termin, zostają oznaczone jako „termin przesunięty",
4. commituje zmiany w `data/events.json` i `feed.xml`,
5. publikuje portal na GitHub Pages,
6. wypisuje podsumowanie w zakładce *Summary* danego przebiegu.

## Jak działa potok danych

```
                    ┌─────────────────────────────────────┐
   scripts/         │  collect.py  (orkiestrator)         │
   sources/  ──────▶│                                     │
                    │  1. gather()    zbierz ze źródeł    │
   sky.py           │  2. normalize() ujednolić wpisy     │
   launches.py      │  3. merge()     scal z poprzednim   │
   spaceweather.py  │  4. prune()     odetnij stare       │
   neo.py           │  5. zapisz JSON + RSS               │
   apod.py          └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
      data/events.json     data/archive/YYYY.json    feed.xml
              │
              ▼
      index.html + assets/app.js   ← to czyta przeglądarka
```

Portal nie ma backendu: przeglądarka pobiera jeden statyczny plik
`data/events.json` i renderuje go po swojej stronie. Cała „inteligencja"
dzieje się raz na dobę w GitHub Actions.

### Co dokładnie robi scalanie

Najciekawszy krok to `merge()` – bez niego portal co dzień gubiłby historię
i migotał przy każdej awarii API.

| Sytuacja | Zachowanie |
|---|---|
| Wpis pojawia się pierwszy raz | dostaje `added_on` = dzisiaj, w portalu plakietkę **nowy wpis** |
| Wpis był już wcześniej | zachowuje pierwotne `added_on`, treść aktualizuje się |
| Źródło zwróciło błąd | jego dotychczasowe wpisy **zostają** z poprzedniego przebiegu |
| Start rakiety przełożony o ≥ 10 min | `rescheduled_from` + plakietka **termin przesunięty** |
| Zjawisko liczone lokalnie „drgnęło" o sekundy | ignorowane – to szum numeryczny, nie zmiana terminu |
| Wydarzenie starsze niż 60 dni | wędruje do `data/archive/<rok>.json` |
| Prognoza pogody kosmicznej (`ephemeral`) | nigdy nie trafia do archiwum ani nie jest wskrzeszana |

Identyfikator wpisu (`id`) jest **stabilny między przebiegami**: dla źródeł
zewnętrznych bierzemy ich własne ID, dla reszty liczymy skrót z kategorii,
tytułu i daty dziennej. Dzięki temu przesunięcie startu o kilka godzin
aktualizuje istniejący wpis, zamiast tworzyć duplikat.

## Skąd biorą się wpisy

| Kategoria | Źródło | Klucz API |
|---|---|---|
| ✨ **Niebo nad nami** – fazy Księżyca, koniunkcje, opozycje, elongacje, równonoce, peryhelium | własne obliczenia (`scripts/ephem.py`) | nie trzeba |
| ☄️ **Roje meteorów i zaćmienia** | dane redagowane w `data/static/` | nie trzeba |
| 🚀 **Starty rakiet** | [The Space Devs / Launch Library 2](https://thespacedevs.com/) | nie trzeba |
| 🌌 **Pogoda kosmiczna i zorze** | [NOAA SWPC](https://www.swpc.noaa.gov/) | nie trzeba |
| ☄️ **Bliskie przeloty planetoid** | [NASA NeoWs](https://api.nasa.gov/) | opcjonalny |
| 🖼️ **Zdjęcie dnia** | [NASA APOD](https://apod.nasa.gov/) | opcjonalny |

Najważniejsza część – kalendarz zjawisk astronomicznych – liczona jest **lokalnie**,
z klasycznych formuł orbitalnych. Dzięki temu portal działa nawet wtedy, gdy
wszystkie zewnętrzne API akurat milczą. Daty faz Księżyca, opozycji i równonocy
zgadzają się z oficjalnymi efemerydami z dokładnością do kilku minut
(np. równonoc jesienna 2026: wyliczone 23.09 00:06 UTC, faktyczne 00:05 UTC).

Jeśli któreś źródło padnie, jego dotychczasowe wpisy **zostają zachowane** z
poprzedniego przebiegu, a w stopce portalu pojawia się informacja, że źródło jest
chwilowo niedostępne.

## Jak liczone są zjawiska astronomiczne

Moduł `scripts/ephem.py` to samodzielny silnik efemeryd na bibliotece
standardowej – żadnych `numpy`, `skyfield` czy plików z danymi JPL.

**Metoda.** Dla każdego ciała bierzemy elementy orbity jako funkcje liniowe
czasu, rozwiązujemy równanie Keplera iteracyjnie, przechodzimy na współrzędne
heliocentryczne i dodajemy wektor Ziemia–Słońce, żeby otrzymać pozycję
geocentryczną. Do Księżyca dokładamy 12 głównych wyrazów perturbacyjnych
(ewekcja, wariacja, równanie roczne…), a do Jowisza, Saturna i Urana –
perturbacje wzajemne. Momenty zjawisk znajdujemy numerycznie: bisekcją
(przejście przez zadany kąt) albo złotym podziałem (ekstremum funkcji).

**Co jest wykrywane automatycznie:**

| Zjawisko | Kryterium | Waga |
|---|---|---|
| Fazy Księżyca | różnica długości Księżyc–Słońce = 0°, 90°, 180°, 270° | 1–2 |
| Superpełnia / mikropełnia | pełnia przy odległości < 360 000 km / > 405 000 km | 3 / 2 |
| Koniunkcja dwóch planet | minimum separacji ≤ 4° | 3–4 |
| Zbliżenie Księżyca do planety | minimum separacji ≤ 3° | 2 |
| Maksymalna elongacja Merkurego / Wenus | maksimum odległości kątowej od Słońca | 4 / 3 |
| Opozycja planety zewnętrznej | długość planety = długość Słońca + 180° | 3–5 |
| Równonoce i przesilenia | długość ekliptyczna Słońca = 0°, 90°, 180°, 270° | 3 |
| Peryhelium i aphelium Ziemi | ekstremum odległości Ziemia–Słońce | 2 |

Zjawiska zbyt blisko Słońca (elongacja < 12°) są odrzucane – i tak nikt ich
nie zobaczy w blasku dnia.

**Dokładność.** Pozycje mają błąd rzędu 1–2′ dla Słońca i Księżyca oraz do
~0,2° dla planet zewnętrznych. Do wyznaczania **dat i godzin** zjawisk to w
zupełności wystarcza. Kontrolne porównania z oficjalnymi efemerydami:

| Zjawisko | AstroAlert | Wartość referencyjna |
|---|---|---|
| Równonoc jesienna 2026 | 23.09, 00:06 UTC | 23.09, 00:05 UTC |
| Opozycja Jowisza | 10.01.2026 | 10.01.2026 |
| Opozycja Marsa | 19.02.2027 | 19.02.2027 |

Testy w `tests/test_ephem.py` pilnują tego automatycznie – sprawdzają nie
tylko konkretne daty, ale i niezmienniki fizyczne: długość miesiąca
synodycznego (29,53 dnia), maksymalną elongację Merkurego (< 29°) i Wenus
(< 48°) czy zakres odległości Księżyca (352 000–407 000 km).

## Dwie wersje językowe

Portal działa po polsku i po angielsku. Wersję wybiera przełącznik **PL / EN**
w nagłówku, a przy pierwszej wizycie decyduje język przeglądarki; wybór zapisuje
się w `localStorage` i w adresie (`?lang=en`), więc da się wysłać komuś link
od razu w jego języku.

**Tłumaczenia nie powstają w przeglądarce ani w żadnym API.** Kolektor uruchamia
się raz na dobę, więc taniej jest wygenerować obie wersje od razu: każde pole
tekstowe wpisu jest obiektem `{"pl": "…", "en": "…"}`. Dzięki temu portal nie
potrzebuje usługi tłumaczącej, a teksty są pisane ręcznie, nie maszynowo.

### Gdzie leżą teksty

| Warstwa | Plik |
|---|---|
| Opisy wydarzeń, nazwy planet, gwiazdozbiorów, etykiety odnośników | [`data/locales/pl.json`](data/locales/pl.json), [`data/locales/en.json`](data/locales/en.json) |
| Roje meteorów i zaćmienia | `data/static/*.json` – pola `name`, `description`, `visibility` są obiektami z kluczami języków |
| Interfejs portalu (nagłówki, filtry, stopka) | słownik `UI` w [`assets/app.js`](assets/app.js) |

W kodzie źródeł nie ma już ani jednego zdania – zostaje sama astronomia:

```python
render("moon.summary", phase=render("moon.phase.full"),
       zodiac=_zodiac(m["lon"]), dist=fmt(dist, 0))
# -> {"pl": "Księżyc wchodzi w fazę pełni w gwiazdozbiorze Wodnika…",
#     "en": "The Moon reaches full phase in Aquarius…"}
```

Parametry mogą być zwykłymi wartościami albo obiektami `{"pl": …, "en": …}` –
te drugie rozwijają się osobno dla każdego języka, co pozwala odmieniać nazwy
(*koniunkcja **Marsa** i **Jowisza*** kontra *conjunction of **Mars** and **Jupiter***).
Liczby też: `fmt()` zwraca `1 234,57` po polsku i `1,234.57` po angielsku.

Daty, nazwy miesięcy i odliczanie („za 3 dni" / „in 3 days") formatuje `Intl`
w przeglądarce, więc odmiana liczebników nie wymaga własnych reguł.

### Dodanie kolejnego języka

1. Dopisz kod języka do `LANGS` w [`scripts/lib/i18n.py`](scripts/lib/i18n.py).
2. Skopiuj `data/locales/pl.json` na `data/locales/<kod>.json` i przetłumacz wartości.
3. Uzupełnij pola językowe w `data/static/*.json`.
4. Dodaj sekcję do słownika `UI` w `assets/app.js` i wpis w `LOCALES` (kod BCP 47).

Testy w [`tests/test_i18n.py`](tests/test_i18n.py) pilnują reszty: sprawdzają, czy
katalogi mają identyczne klucze, czy pola `{w nawiasach}` się nie rozjechały, czy
żaden klucz wołany z kodu nie zniknął i czy słownik interfejsu obejmuje wszystkie
języki. Kanał RSS powstaje osobno dla każdego języka (`feed.xml`, `feed.en.xml`).

### Czego nie tłumaczymy

Opisy misji z Launch Library i tytuły zdjęć NASA przychodzą z API wyłącznie po
angielsku i zostają w oryginale także w polskiej wersji – tłumaczenie ich
wymagałoby zewnętrznej usługi, a portal ma działać bez żadnych kluczy API.
Nazwy własne (rakiety, kosmodromy, oznaczenia katalogowe planetoid) są wspólne
dla obu wersji.

## Uruchomienie u siebie

1. Zrób forka lub sklonuj repozytorium.
2. **Settings → Pages → Source: GitHub Actions**.
3. **Settings → Actions → General → Workflow permissions: Read and write permissions**
   (bot musi móc zapisywać zaktualizowane dane).
4. Zakładka **Actions → Codzienna aktualizacja wydarzeń → Run workflow** – pierwszy
   przebieg zaraz po włączeniu, bez czekania na harmonogram.

### Opcjonalnie: własny klucz NASA

Bez klucza używany jest `DEMO_KEY` (limit 50 zapytań dziennie – dla jednego
przebiegu na dobę w zupełności wystarcza, ale bywa przeciążony).
Darmowy klucz z [api.nasa.gov](https://api.nasa.gov/) dodaj jako sekret
**Settings → Secrets and variables → Actions → New repository secret**
o nazwie `NASA_API_KEY`.

## Praca lokalna

```bash
python3 scripts/collect.py --offline     # tylko obliczenia astronomiczne, bez sieci
python3 scripts/collect.py               # pełny przebieg
python3 scripts/collect.py --dry-run     # bez zapisywania plików
python3 -m unittest discover -s tests    # 99 testów
python3 -m http.server 8000              # podgląd portalu na http://localhost:8000
```

Portal to statyczny HTML + jeden plik CSS i jeden JS – bez frameworków,
bez kroku budowania i bez zewnętrznych zasobów (wszystko ładuje się z Twojej domeny).

## Dodanie własnego źródła danych

Źródło to zwykły moduł w `scripts/sources/` z funkcją `collect()` zwracającą
listę słowników. Nie musi znać reszty systemu – normalizacją, identyfikatorami
i scalaniem zajmuje się `collect.py`.

```python
# scripts/sources/moje_zrodlo.py
from datetime import datetime

from lib.http import get_json          # klient z ponowieniami i timeoutem
from lib.i18n import literal, render    # teksty w obu językach naraz
from lib.text import fmt                # liczby: "8,46" po polsku, "8.46" po angielsku


def collect(now: datetime) -> list[dict]:
    data = get_json("https://przyklad.pl/api/wydarzenia.json")
    return [
        {
            "title": literal(item["name"]),     # nazwa własna – ta sama w obu wersjach
            "starts_at": item["date"],          # ISO 8601, zawsze UTC
            "category": "mission",              # sky | launch | spaceweather | asteroid | mission
            "importance": 4,                    # 1–5, od tego zależy filtr i hero
            "summary": render("moje.opis", cel=literal(item["target"])),
            "tags": [render("tag.probe")],
            "links": [{"label": render("link.launch_details"), "url": item["url"]}],
            "source": render("attribution.moje-zrodlo"),
            "source_id": "moje-zrodlo",         # stały identyfikator techniczny
            "uid": f"moje-{item['id']}",        # opcjonalnie: stabilne ID wpisu
        }
        for item in data["results"]
    ]
```

Klucze `moje.opis`, `attribution.moje-zrodlo` dopisujesz do
`data/locales/pl.json` i `data/locales/en.json` – test parzystości kluczy
przypomni, jeśli któryś zostanie tylko w jednym pliku.

Następnie zarejestruj je w `scripts/collect.py`, w funkcji `gather()`:

```python
run("moje-zrodlo", "Moje źródło", lambda: moje_zrodlo.collect(now))
```

Co dostajesz za darmo:

- **odporność** – wyjątek z `collect()` nie wywraca przebiegu, tylko oznacza
  źródło jako niedostępne (a jego stare wpisy zostają na portalu),
- **ponowienia** – `get_json()` wykonuje do trzech prób z rosnącym odstępem,
  obsługuje gzip i nie ponawia bezsensownie przy 400/401/403/404,
- **kategoria w portalu** – filtry, kolory i ikony biorą się z `category`.

Jeżeli wpisy są krótkoterminowymi prognozami, dodaj `"ephemeral": True` – nie
będą archiwizowane ani przywracane po awarii źródła.

Na koniec dopisz test na zapisanej odpowiedzi API (wzór:
`tests/test_sources.py` + plik w `tests/fixtures/`). Dzięki temu testy działają
bez sieci, a zmiana schematu API od razu rzuca się w oczy.

## Dopisywanie własnych wpisów

Do `data/custom_events.json` możesz dodać wydarzenia, których nie ma w żadnym API –
premierę misji, wykład, zlot obserwatorów:

```json
[
  {
    "title": {
      "pl": "Start misji Ariel (ESA)",
      "en": "Launch of ESA's Ariel mission"
    },
    "starts_at": "2029-06-15T12:00:00Z",
    "category": "mission",
    "importance": 5,
    "summary": {
      "pl": "Teleskop kosmiczny ESA, który zbada atmosfery tysiąca egzoplanet.",
      "en": "An ESA space telescope that will survey the atmospheres of a thousand exoplanets."
    },
    "tags": [{"pl": "ESA", "en": "ESA"}],
    "links": [{"label": {"pl": "Strona misji", "en": "Mission website"},
               "url": "https://arielmission.space/"}]
  }
]
```

Pola tekstowe wolno też podać zwykłym napisem – wtedy ten sam tekst trafi do
wszystkich wersji językowych, co bywa wygodne przy szybkim wpisie.

Wpisy przetrwają kolejne aktualizacje – automat ich nie nadpisuje.

Podobnie działają pliki w `data/static/`:
[`meteor_showers.json`](data/static/meteor_showers.json) (roje powtarzają się co roku,
więc wystarczy raz podać datę maksimum) oraz
[`eclipses.json`](data/static/eclipses.json) (zaćmienia do 2030 roku – warto
je uzupełniać z [katalogu NASA](https://eclipse.gsfc.nasa.gov/eclipse.html)).

## Dostrajanie

Wszystkie progi siedzą w stałych na górze modułów – nie trzeba szukać po kodzie.

| Co chcesz zmienić | Gdzie | Domyślnie |
|---|---|---|
| Godzina codziennej aktualizacji | `cron` w `.github/workflows/daily-update.yml` | `20 4 * * *` (04:20 UTC) |
| Jak daleko w przyszłość liczyć | `--days` w tym samym workflow | 400 dni |
| Jak długo trzymać minione wydarzenia | `KEEP_PAST_DAYS` w `collect.py` | 60 dni |
| Próg „termin przesunięty" | `RESCHEDULE_THRESHOLD` w `collect.py` | 10 minut |
| Czułość na koniunkcje | `PLANET_PAIRS_MAX_SEP`, `MOON_PAIR_MAX_SEP` w `sources/sky.py` | 4° i 3° |
| Które starty są ważne | słownik `HIGHLIGHTS` w `sources/launches.py` | załoga, Księżyc, Mars, nowe rakiety |
| Od jakiej burzy informować o zorzy | `if level < 5` w `sources/spaceweather.py` | Kp ≥ 5 (G1) |
| Które planetoidy pokazywać | `CLOSE_LD`, `MAX_RANKED`, `MIN_DIAMETER_M` w `sources/neo.py` | wszystkie bliżej niż 5 odl. Księżyca + 5 największych dalszych |
| Nazwy i kolejność kategorii | `CATEGORY_LABELS` w `collect.py` | 5 kategorii |
| Kolory i ikony kategorii | `CATEGORY_COLORS`, `CATEGORY_ICONS` w `assets/app.js` oraz zmienne `--cat-*` w `assets/style.css` | motyw nocnego nieba |

Skala `importance` (1–5) steruje trzema rzeczami naraz: filtrem **„tylko
najciekawsze"** (pokazuje ≥ 4), wyborem wydarzenia do sekcji hero z odliczaniem
(pierwsze nadchodzące ≥ 4) oraz listą w podsumowaniu przebiegu workflow.
Gwiazdki przy wpisie to właśnie ta wartość.

### Portal

`assets/app.js` to jeden plik bez zależności i bez kroku budowania. Warto
wiedzieć, że:

- godziny w danych są **zawsze w UTC**, a przeglądarka przelicza je na strefę
  odwiedzającego (stopka pokazuje jaką),
- wydarzenia znikają z listy dopiero **6 godzin po rozpoczęciu** – zaćmienie
  sprzed godziny wciąż widać,
- wyszukiwarka filtruje po tytule, opisie, tagach i miejscu; wiele słów działa
  jak koniunkcja („perseidy 2027"),
- każdy wpis ma własny `id` w URL-u, więc `…/#opozycja-saturna-2026-10-04-1a2b3c4d`
  prowadzi prosto do niego (tak samo linkuje kanał RSS).

## Struktura repozytorium

```
index.html              portal (statyczny, dwujęzyczny)
assets/                 style.css, app.js
scripts/
  collect.py            orkiestrator: zbiera, scala, zapisuje, generuje RSS
  ephem.py              efemerydy: Słońce, Księżyc, planety
  sources/
    sky.py              zjawiska liczone lokalnie
    launches.py         starty rakiet
    spaceweather.py     burze geomagnetyczne i zorze
    neo.py              bliskie przeloty planetoid
    apod.py             zdjęcie dnia
  lib/                  klient HTTP, katalog tłumaczeń, formatowanie liczb
data/
  events.json           wynik – to czyta portal
  locales/              teksty portalu: pl.json, en.json
  custom_events.json    Twoje własne wpisy
  static/               roje meteorów, zaćmienia
  archive/              wydarzenia starsze niż 60 dni, rocznikami
tests/                  99 testów (efemerydy, parsery API, scalanie, katalog tłumaczeń)
```

Cały kod używa wyłącznie biblioteki standardowej Pythona – nie ma czego instalować.

## Format danych

```jsonc
{
  "generated_at": "2026-08-30T04:20:11Z",
  "languages": ["pl", "en"],
  "sources":  [ { "id": "swpc", "name": "…", "status": "ok", "count": 3 } ],
  "apod":     { "title": "…", "image": "…", "credit": "…" },
  "stats":    { "total": 132, "upcoming": 128, "new_today": 4 },
  "events": [
    {
      "id": "opozycja-saturna-2026-10-04-1a2b3c4d",
      "title": { "pl": "Opozycja Saturna", "en": "Saturn at opposition" },
      "starts_at": "2026-10-04T11:57:00Z",   // zawsze UTC, portal przelicza na czas lokalny
      "category": "sky",                      // sky | launch | spaceweather | asteroid | mission
      "importance": 5,                        // 1–5, portal filtruje po tym „tylko najciekawsze"
      "summary": { "pl": "…", "en": "…" },   // każde pole tekstowe ma wersje językowe
      "tags": [ { "pl": "Saturn", "en": "Saturn" } ],
      "links": [ { "label": { "pl": "…", "en": "…" }, "url": "…" } ],
      "extra": { "body": "Saturn" },          // identyfikatory maszynowe, bez tłumaczeń
      "source": { "pl": "…", "en": "…" },
      "added_on": "2026-08-30"                // stąd plakietka „nowy wpis"
    }
  ]
}
```

## Rozwiązywanie problemów

| Objaw | Przyczyna i naprawa |
|---|---|
| Workflow kończy się błędem na kroku `configure-pages` | Pages nie są włączone albo mają złe źródło → **Settings → Pages → Source: GitHub Actions** |
| `Permission denied` przy `git push` w workflow | **Settings → Actions → General → Workflow permissions: Read and write permissions** |
| Portal pokazuje „Nie udało się wczytać danych" | otwierasz `index.html` z dysku – przeglądarka blokuje `fetch` po `file://`. Uruchom `python3 -m http.server` |
| Stopka: „NASA NeoWs – chwilowo niedostępne" | wyczerpany limit `DEMO_KEY` (50/dobę, wspólny dla całego IP). Dodaj sekret `NASA_API_KEY` |
| Stopka: „Starty rakiet – chwilowo niedostępne" | Launch Library ma limit ~15 zapytań/godzinę na IP; przy jednym przebiegu na dobę zwykle mija samo. Poprzednie wpisy zostają widoczne |
| Brak startów rakiet mimo działającego źródła | rutynowe Starlinki mają wagę 1 – odznacz **„tylko najciekawsze"** |
| Codzienny commit się nie pojawia | to normalne, gdy dane się nie zmieniły – workflow wtedy nie commituje (widać w logu „Brak zmian w danych") |
| Zmiany w danych są, ale portal pokazuje stare | cache przeglądarki; strona dopisuje znacznik czasu do zapytania, więc wystarczy odświeżenie |
| Godziny nie zgadzają się o 1–2 h | dane są w UTC, portal przelicza na strefę lokalną – porównuj z tym, co pokazuje strona, nie z surowym JSON-em |

Diagnostyka zaczyna się w dwóch miejscach: zakładka **Actions → Summary**
danego przebiegu (tabela ze statusem każdego źródła i lista najbliższych
wydarzeń) oraz **stopka portalu**, która pokazuje ten sam stan odwiedzającym.

## Uwagi i ograniczenia

- Efemerydy są **niskiej precyzji** (błąd pozycji do ~0,2° dla planet zewnętrznych).
  Do wyznaczania dat zjawisk to bez znaczenia, ale nie używaj ich do celowania teleskopem.
- Widoczność zjawisk opisujemy z perspektywy **Polski / średnich szerokości północnych**.
- Godziny startów rakiet zmieniają się notorycznie – zawsze sprawdź status przed transmisją.
- Zaćmienia i roje pochodzą z tabel redagowanych ręcznie; tabelę zaćmień warto
  przedłużyć po 2030 roku.

---

Dane: NASA, NOAA SWPC, The Space Devs. Kod na licencji MIT.
