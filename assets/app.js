/* AstroAlert - warstwa prezentacji. Czysty JS, bez bibliotek i bez budowania.
 *
 * Dane przychodzą już we wszystkich językach: każde pole tekstowe wpisu jest
 * obiektem {pl: "…", en: "…"}. Tutaj wybieramy tylko właściwą wersję, a daty
 * i liczebniki formatuje Intl - dzięki temu odmiana ("za 3 dni" / "in 3 days")
 * nie wymaga własnych reguł gramatycznych.
 */
(() => {
  "use strict";

  const DEFAULT_LANG = "pl";
  const LOCALES = { pl: "pl-PL", en: "en-GB" };

  const UI = {
    pl: {
      tagline: "Co ciekawego dzieje się nad naszymi głowami",
      updated: "Aktualizacja:",
      heroEyebrow: "Najbliższe wielkie wydarzenie",
      apodEyebrow: "Zdjęcie dnia NASA",
      searchPlaceholder: "Szukaj: Perseidy, Saturn, zaćmienie, Falcon…",
      searchLabel: "Szukaj wydarzeń",
      onlyBig: "Tylko najciekawsze",
      showPast: "Pokaż minione",
      loading: "Wczytywanie danych…",
      empty: "Nic nie pasuje do tych filtrów. Spróbuj wyczyścić wyszukiwanie.",
      viewAll: "Wszystkie wydarzenia",
      viewPoland: "🇵🇱 Widoczne z Polski",
      viewPolandHint: "Najciekawsze zjawiska, które da się obserwować z Polski " +
        "– widoczność liczona dla środka kraju",
      bestTime: "najwyżej o {time}",
      sourcesHeading: "Skąd pochodzą dane",
      aboutHeading: "O portalu",
      about: "Zjawiska na niebie – fazy Księżyca, koniunkcje, opozycje, elongacje, " +
        "równonoce – wyliczamy sami z efemeryd, więc kalendarz działa nawet wtedy, gdy " +
        "zewnętrzne API milczą. Starty rakiet, pogodę kosmiczną i przeloty planetoid " +
        "dociągamy z otwartych źródeł raz na dobę.",
      timezone: "Godziny podajemy w Twojej strefie czasowej ({tz}). Kod i dane są otwarte – ",
      repo: "zobacz repozytorium",
      badgeNew: "nowy wpis",
      badgeMoved: "termin przesunięty",
      rating: "Ocena atrakcyjności: {n}/5",
      status: { ok: "działa", error: "chwilowo niedostępne", skipped: "pominięte" },
      countdown: ["dni", "godz.", "min", "sek."],
      loadError: "Nie udało się wczytać danych ({error}). Jeśli otwierasz plik lokalnie, " +
        "uruchom serwer: <code>python3 -m http.server</code>.",
      langName: "Polski",
    },
    en: {
      tagline: "What's going on above our heads",
      updated: "Updated:",
      heroEyebrow: "Next big event",
      apodEyebrow: "NASA picture of the day",
      searchPlaceholder: "Search: Perseids, Saturn, eclipse, Falcon…",
      searchLabel: "Search events",
      onlyBig: "Highlights only",
      showPast: "Show past events",
      loading: "Loading data…",
      empty: "Nothing matches these filters. Try clearing the search box.",
      viewAll: "All events",
      viewPoland: "🇵🇱 Visible from Poland",
      viewPolandHint: "The best events observable from Poland " +
        "– visibility computed for the centre of the country",
      bestTime: "highest at {time}",
      sourcesHeading: "Where the data comes from",
      aboutHeading: "About",
      about: "Sky events – lunar phases, conjunctions, oppositions, elongations and " +
        "equinoxes – are computed here from ephemerides, so the calendar keeps working " +
        "even when every external API is down. Rocket launches, space weather and " +
        "asteroid passes are pulled from open sources once a day.",
      timezone: "Times are shown in your own time zone ({tz}). The code and the data are open – ",
      repo: "browse the repository",
      badgeNew: "new entry",
      badgeMoved: "rescheduled",
      rating: "Interest rating: {n}/5",
      status: { ok: "working", error: "temporarily unavailable", skipped: "skipped" },
      countdown: ["days", "hrs", "min", "sec"],
      loadError: "Could not load the data ({error}). If you opened the file from disk, " +
        "start a server: <code>python3 -m http.server</code>.",
      langName: "English",
    },
  };

  const CATEGORY_COLORS = {
    sky: "var(--cat-sky)", launch: "var(--cat-launch)",
    spaceweather: "var(--cat-spaceweather)", asteroid: "var(--cat-asteroid)",
    mission: "var(--cat-mission)",
  };
  const CATEGORY_ICONS = {
    sky: "✨", launch: "🚀", spaceweather: "🌌", asteroid: "☄️", mission: "🛰️",
  };

  const el = (id) => document.getElementById(id);
  const state = {
    doc: null, events: [], categories: {}, languages: [DEFAULT_LANG],
    lang: DEFAULT_LANG, view: "all", active: new Set(), query: "", onlyBig: false,
    showPast: false,
    today: new Date().toISOString().slice(0, 10), countdownTimer: null,
  };

  /* --- język ------------------------------------------------------------ */

  /** Tekst wielojęzyczny -> napis w bieżącym języku (znosi też zwykłe napisy). */
  const pickText = (value) => {
    if (value == null) return "";
    if (typeof value === "string") return value;
    return value[state.lang] ?? value[DEFAULT_LANG] ?? "";
  };

  const ui = () => UI[state.lang] || UI[DEFAULT_LANG];
  const locale = () => LOCALES[state.lang] || LOCALES[DEFAULT_LANG];

  /** Kolejność: wybór użytkownika > parametr w adresie > język przeglądarki. */
  function initialLang(available) {
    const fromUrl = new URLSearchParams(location.search).get("lang");
    if (available.includes(fromUrl)) return fromUrl;
    let saved = null;
    try { saved = localStorage.getItem("astroalert-lang"); } catch (e) { /* prywatne okno */ }
    if (available.includes(saved)) return saved;
    for (const tag of navigator.languages || [navigator.language || ""]) {
      const base = String(tag).slice(0, 2).toLowerCase();
      if (available.includes(base)) return base;
    }
    return available.includes(DEFAULT_LANG) ? DEFAULT_LANG : available[0];
  }

  function setLang(lang) {
    state.lang = lang;
    try { localStorage.setItem("astroalert-lang", lang); } catch (e) { /* nieistotne */ }
    document.documentElement.lang = lang;
    const url = new URL(location.href);
    url.searchParams.set("lang", lang);
    history.replaceState(null, "", url);
    renderAll();
  }

  /* --- formatowanie ------------------------------------------------------ */

  const parse = (iso) => new Date(iso);

  const dtf = (opts) => new Intl.DateTimeFormat(locale(), opts);

  const formatDate = (d) => dtf({
    day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(d);

  const formatTime = (d) => dtf({ hour: "2-digit", minute: "2-digit" }).format(d);

  /** Intl sam dobiera liczebnik i przyimek w każdym języku. */
  function relative(d, now) {
    const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });
    const diff = d - now;
    const abs = Math.abs(diff);
    const day = 86400000;
    const sign = diff < 0 ? -1 : 1;
    if (abs < 3600000) return rtf.format(sign * Math.max(1, Math.round(abs / 60000)), "minute");
    if (abs < day) return rtf.format(sign * Math.round(abs / 3600000), "hour");
    if (abs < 60 * day) return rtf.format(sign * Math.round(abs / day), "day");
    return rtf.format(sign * Math.round(abs / (30.44 * day)), "month");
  }

  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const fill = (template, values) =>
    template.replace(/\{(\w+)\}/g, (_, key) => values[key] ?? "");

  const linksHtml = (links) => (links || [])
    .map((l) => `<a href="${escapeHtml(pickText(l.url))}" target="_blank" rel="noopener">` +
                `${escapeHtml(pickText(l.label))}</a>`).join("");

  /* --- karty wydarzeń ---------------------------------------------------- */

  function eventCard(ev, now) {
    const d = parse(ev.starts_at);
    const past = d < now;
    const stars = "★".repeat(ev.importance) + "☆".repeat(5 - ev.importance);
    const isNew = ev.added_on === state.today && !past;
    const T = ui();

    const badges = [
      `<span class="badge">${CATEGORY_ICONS[ev.category] || "•"} ` +
        `${escapeHtml(pickText(state.categories[ev.category]) || ev.category)}</span>`,
      isNew ? `<span class="badge new">${escapeHtml(T.badgeNew)}</span>` : "",
      ev.rescheduled_from ? `<span class="badge moved">${escapeHtml(T.badgeMoved)}</span>` : "",
      `<span class="stars" title="${escapeHtml(fill(T.rating, { n: ev.importance }))}">${stars}</span>`,
      past ? "" : `<span class="countdown-inline">${escapeHtml(relative(d, now))}</span>`,
    ].join("");

    const tags = (ev.tags || []).slice(0, 4)
      .map((t) => `<span class="tag">${escapeHtml(pickText(t))}</span>`).join("");
    const place = ev.location
      ? `<span class="tag">📍 ${escapeHtml(pickText(ev.location))}</span>` : "";

    // notatkę o widoczności pokazujemy tylko w zakładce krajowej - w widoku
    // ogólnym powtarzałaby się przy prawie każdym wpisie
    let polandNote = "";
    if (state.view === "poland" && ev.poland && ev.poland.note) {
      const when = ev.poland.best_time
        ? `<span class="when">${escapeHtml(fill(T.bestTime,
            { time: formatTime(parse(ev.poland.best_time)) }))}</span>` : "";
      polandNote = `<p class="poland-note"><span>${escapeHtml(pickText(ev.poland.note))}</span>${when}</p>`;
    }

    return `<article class="event${past ? " past" : ""}" id="${escapeHtml(ev.id)}" ` +
      `style="--cat:${CATEGORY_COLORS[ev.category] || "var(--accent)"}">
      <div class="date-badge">
        <span class="day">${dtf({ day: "numeric" }).format(d)}</span>
        <span class="mon">${escapeHtml(dtf({ month: "short" }).format(d))}</span>
        <span class="time">${escapeHtml(formatTime(d))}</span>
      </div>
      <div>
        <h3>${escapeHtml(pickText(ev.title))}</h3>
        <div class="meta">${badges}</div>
        <p>${escapeHtml(pickText(ev.summary))}</p>
        ${polandNote}
        <div class="meta">${tags}${place}</div>
        <div class="links">${linksHtml(ev.links)}</div>
      </div>
    </article>`;
  }

  /** Czy wpis należy do zakładki "Widoczne z Polski"? */
  const isPolish = (ev) => Boolean(ev.poland && ev.poland.visible) && ev.importance >= 3;

  /** @param ignoreCategory - do liczenia etykiet przy filtrach kategorii */
  function matches(ev, now, ignoreCategory) {
    if (state.view === "poland" && !isPolish(ev)) return false;
    if (!state.showPast && parse(ev.starts_at) < now - 6 * 3600000) return false;
    if (state.onlyBig && ev.importance < 4) return false;
    if (!ignoreCategory && state.active.size && !state.active.has(ev.category)) return false;
    if (state.query) {
      const hay = [pickText(ev.title), pickText(ev.summary), pickText(ev.location),
        ...(ev.tags || []).map(pickText)].join(" ").toLowerCase();
      if (!state.query.split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  function updateCounts(now) {
    const counts = {};
    for (const ev of state.events) {
      if (matches(ev, now, true)) counts[ev.category] = (counts[ev.category] || 0) + 1;
    }
    for (const chip of el("filters").querySelectorAll(".chip")) {
      const n = counts[chip.dataset.cat] || 0;
      chip.querySelector(".count").textContent = n;
      chip.hidden = n === 0 && !state.active.has(chip.dataset.cat);
    }
  }

  function renderTimeline() {
    const now = new Date();
    const visible = state.events.filter((ev) => matches(ev, now, false));
    updateCounts(now);
    el("empty").hidden = visible.length > 0;

    const monthFmt = dtf({ month: "long", year: "numeric" });
    let html = "";
    let currentMonth = "";
    for (const ev of visible) {
      const key = monthFmt.format(parse(ev.starts_at));
      if (key !== currentMonth) {
        currentMonth = key;
        html += `<h2 class="month">${escapeHtml(key)}</h2>`;
      }
      html += eventCard(ev, now);
    }
    el("timeline").innerHTML = html;
    el("status").hidden = true;
    renderViews();
  }

  /* --- pozostałe sekcje -------------------------------------------------- */

  function renderChrome() {
    const T = ui();
    document.documentElement.lang = state.lang;
    document.title = pickText(state.doc?.site?.title) || "AstroAlert";
    el("tagline").textContent = T.tagline;
    el("updated-label").textContent = T.updated;
    el("hero-eyebrow").textContent = T.heroEyebrow;
    el("apod-eyebrow").textContent = T.apodEyebrow;
    el("search").placeholder = T.searchPlaceholder;
    el("search").setAttribute("aria-label", T.searchLabel);
    el("only-big-label").textContent = T.onlyBig;
    el("show-past-label").textContent = T.showPast;
    el("empty").textContent = T.empty;
    el("sources-heading").textContent = T.sourcesHeading;
    el("about-heading").textContent = T.aboutHeading;
    el("about-text").textContent = T.about;
    el("feed-link").href = state.lang === DEFAULT_LANG ? "feed.xml" : `feed.${state.lang}.xml`;

    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    el("about-tz").innerHTML = escapeHtml(fill(T.timezone, { tz })) +
      `<a href="https://github.com/ClaudePlos/AstroAlert">${escapeHtml(T.repo)}</a>.`;

    const gen = parse(state.doc.generated_at);
    el("generated").textContent = `${formatDate(gen)} (${relative(gen, new Date())})`;
    el("generated").dateTime = state.doc.generated_at;
  }

  function renderLangSwitch() {
    el("lang-switch").innerHTML = state.languages.map((lang) =>
      `<button type="button" data-lang="${lang}" aria-pressed="${lang === state.lang}" ` +
      `title="${escapeHtml((UI[lang] || {}).langName || lang)}">${lang.toUpperCase()}</button>`
    ).join("");
  }

  function renderViews() {
    const T = ui();
    const now = new Date();
    const counts = {
      all: state.events.filter((ev) => state.showPast
        || parse(ev.starts_at) >= now - 6 * 3600000).length,
      poland: state.events.filter((ev) => isPolish(ev)
        && (state.showPast || parse(ev.starts_at) >= now - 6 * 3600000)).length,
    };
    el("views").innerHTML = [
      ["all", T.viewAll, ""],
      ["poland", T.viewPoland, T.viewPolandHint],
    ].map(([key, label, hint]) =>
      `<button type="button" role="tab" data-view="${key}" ` +
      `aria-selected="${state.view === key}" title="${escapeHtml(hint)}">` +
      `${escapeHtml(label)}<span class="count">${counts[key]}</span></button>`
    ).join("");
  }

  function renderFilters() {
    el("filters").innerHTML = Object.entries(state.categories).map(([key, label]) =>
      `<button class="chip" data-cat="${key}" aria-pressed="${state.active.has(key)}">
         ${CATEGORY_ICONS[key] || "•"} ${escapeHtml(pickText(label))}<span class="count">0</span>
       </button>`).join("");
  }

  function renderHero() {
    const now = new Date();
    // kafel idzie za zakładką: w widoku krajowym zapowiada zjawisko,
    // które faktycznie da się zobaczyć z Polski
    const next = state.events
      .filter((ev) => parse(ev.starts_at) > now && ev.importance >= 4
        && (state.view !== "poland" || isPolish(ev)))
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0];
    el("hero").hidden = !next;
    if (!next) return;

    el("hero").hidden = false;
    el("hero-title").textContent = pickText(next.title);
    el("hero-when").textContent = formatDate(parse(next.starts_at)) +
      (next.location ? ` · ${pickText(next.location)}` : "");
    el("hero-summary").textContent = pickText(next.summary);
    el("hero-links").innerHTML = linksHtml(next.links);

    const target = parse(next.starts_at);
    const labels = ui().countdown;
    const tick = () => {
      let left = Math.max(0, target - new Date());
      const days = Math.floor(left / 86400000); left -= days * 86400000;
      const hrs = Math.floor(left / 3600000); left -= hrs * 3600000;
      const mins = Math.floor(left / 60000);
      const secs = Math.floor((left - mins * 60000) / 1000);
      el("hero-countdown").innerHTML = [days, hrs, mins, secs]
        .map((v, i) => `<span><b>${String(v).padStart(2, "0")}</b>` +
                       `<small>${escapeHtml(labels[i])}</small></span>`).join("");
    };
    tick();
    clearInterval(state.countdownTimer);
    state.countdownTimer = setInterval(tick, 1000);
  }

  function renderApod() {
    const pic = state.doc.apod;
    if (!pic || !pic.image) return;
    el("apod").hidden = false;
    el("apod-img").src = pic.image;
    el("apod-img").alt = pic.title || "";
    el("apod-link").href = pic.hdimage || pic.link;
    el("apod-title").textContent = pic.title || "";
    el("apod-credit").textContent = `${pickText(pic.credit) || "NASA"} · ${pic.date || ""}`;
  }

  function renderSources() {
    const labels = ui().status;
    el("sources").innerHTML = (state.doc.sources || []).map((s) =>
      `<li><span class="dot ${s.status}"></span><span>${escapeHtml(pickText(s.name))} – ` +
      `${escapeHtml(labels[s.status] || s.status)}${s.count ? ` (${s.count})` : ""}</span></li>`
    ).join("");
  }

  function renderAll() {
    renderChrome();
    renderLangSwitch();
    renderViews();
    renderFilters();
    renderHero();
    renderApod();
    renderSources();
    renderTimeline();
  }

  /* --- start ------------------------------------------------------------- */

  function bind() {
    let timer;
    el("search").addEventListener("input", (e) => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.query = e.target.value.trim().toLowerCase();
        renderTimeline();
      }, 150);
    });
    el("only-big").addEventListener("change", (e) => {
      state.onlyBig = e.target.checked; renderTimeline();
    });
    el("show-past").addEventListener("change", (e) => {
      state.showPast = e.target.checked; renderTimeline();
    });
    el("filters").addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      const cat = chip.dataset.cat;
      const on = !state.active.has(cat);
      on ? state.active.add(cat) : state.active.delete(cat);
      chip.setAttribute("aria-pressed", String(on));
      renderTimeline();
    });
    el("views").addEventListener("click", (e) => {
      const button = e.target.closest("button[data-view]");
      if (!button || button.dataset.view === state.view) return;
      state.view = button.dataset.view;
      renderHero();
      const url = new URL(location.href);
      state.view === "all" ? url.searchParams.delete("view")
        : url.searchParams.set("view", state.view);
      history.replaceState(null, "", url);
      renderTimeline();
    });
    el("lang-switch").addEventListener("click", (e) => {
      const button = e.target.closest("button[data-lang]");
      if (button && button.dataset.lang !== state.lang) setLang(button.dataset.lang);
    });
  }

  async function init() {
    el("status").textContent = ui().loading;
    try {
      const res = await fetch(`data/events.json?v=${Date.now()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const doc = await res.json();

      state.doc = doc;
      state.events = doc.events || [];
      state.categories = doc.categories || {};
      state.languages = doc.languages || [DEFAULT_LANG];
      state.lang = initialLang(state.languages);
      if (new URLSearchParams(location.search).get("view") === "poland") {
        state.view = "poland";
      }

      bind();
      renderAll();

      if (location.hash) {
        const target = document.getElementById(location.hash.slice(1));
        if (target) target.scrollIntoView();
      }
    } catch (err) {
      el("status").innerHTML = fill(ui().loadError, { error: escapeHtml(err.message) });
    }
  }

  init();
})();
