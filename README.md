# 🔭 AstroAlert

Portal o tym, **co ciekawego dzieje się w kosmosie** – kalendarz zjawisk na niebie
i wydarzeń kosmicznych, który sam się aktualizuje raz na dobę i hostuje się na
GitHub Pages. Zero serwera, zero bazy danych, zero kosztów.

| | |
|---|---|
| **Portal** | `https://<twoja-nazwa>.github.io/AstroAlert` |
| **Kanał RSS** | `/feed.xml` |
| **Dane** | `data/events.json` (otwarte, do użycia w innych projektach) |

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
python3 -m unittest discover -s tests    # 58 testów
python3 -m http.server 8000              # podgląd portalu na http://localhost:8000
```

Portal to statyczny HTML + jeden plik CSS i jeden JS – bez frameworków,
bez kroku budowania i bez zewnętrznych zasobów (wszystko ładuje się z Twojej domeny).

## Dopisywanie własnych wpisów

Do `data/custom_events.json` możesz dodać wydarzenia, których nie ma w żadnym API –
premierę misji, wykład, zlot obserwatorów:

```json
[
  {
    "title": "Start misji Ariel (ESA)",
    "starts_at": "2029-06-15T12:00:00Z",
    "category": "mission",
    "importance": 5,
    "summary": "Teleskop kosmiczny ESA, który zbada atmosfery tysiąca egzoplanet.",
    "tags": ["ESA", "egzoplanety"],
    "links": [{"label": "Strona misji", "url": "https://arielmission.space/"}]
  }
]
```

Wpisy przetrwają kolejne aktualizacje – automat ich nie nadpisuje.

Podobnie działają pliki w `data/static/`:
[`meteor_showers.json`](data/static/meteor_showers.json) (roje powtarzają się co roku,
więc wystarczy raz podać datę maksimum) oraz
[`eclipses.json`](data/static/eclipses.json) (zaćmienia do 2030 roku – warto
je uzupełniać z [katalogu NASA](https://eclipse.gsfc.nasa.gov/eclipse.html)).

## Struktura repozytorium

```
index.html              portal (statyczny)
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
  lib/                  klient HTTP z ponowieniami, formatowanie liczb
data/
  events.json           wynik – to czyta portal
  custom_events.json    Twoje własne wpisy
  static/               roje meteorów, zaćmienia
  archive/              wydarzenia starsze niż 60 dni, rocznikami
tests/                  58 testów (efemerydy, parsery API, scalanie danych)
```

Cały kod używa wyłącznie biblioteki standardowej Pythona – nie ma czego instalować.

## Format danych

```jsonc
{
  "generated_at": "2026-08-30T04:20:11Z",
  "sources":  [ { "id": "swpc", "name": "…", "status": "ok", "count": 3 } ],
  "apod":     { "title": "…", "image": "…", "credit": "…" },
  "stats":    { "total": 132, "upcoming": 128, "new_today": 4 },
  "events": [
    {
      "id": "opozycja-saturna-2026-10-04-1a2b3c4d",
      "title": "Opozycja Saturna",
      "starts_at": "2026-10-04T11:57:00Z",   // zawsze UTC, portal przelicza na czas lokalny
      "category": "sky",                      // sky | launch | spaceweather | asteroid | mission
      "importance": 5,                        // 1–5, portal filtruje po tym „tylko najciekawsze"
      "summary": "…",
      "tags": ["Saturn", "opozycja"],
      "links": [ { "label": "…", "url": "…" } ],
      "source": "obliczenia własne (efemerydy)",
      "added_on": "2026-08-30"                // stąd plakietka „nowy wpis"
    }
  ]
}
```

## Uwagi i ograniczenia

- Efemerydy są **niskiej precyzji** (błąd pozycji do ~0,2° dla planet zewnętrznych).
  Do wyznaczania dat zjawisk to bez znaczenia, ale nie używaj ich do celowania teleskopem.
- Widoczność zjawisk opisujemy z perspektywy **Polski / średnich szerokości północnych**.
- Godziny startów rakiet zmieniają się notorycznie – zawsze sprawdź status przed transmisją.
- Zaćmienia i roje pochodzą z tabel redagowanych ręcznie; tabelę zaćmień warto
  przedłużyć po 2030 roku.

---

Dane: NASA, NOAA SWPC, The Space Devs. Kod na licencji MIT.
