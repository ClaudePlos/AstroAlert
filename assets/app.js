/* AstroAlert - warstwa prezentacji. Czysty JS, bez bibliotek i bez budowania. */
(() => {
  "use strict";

  const CATEGORY_COLORS = {
    sky: "var(--cat-sky)",
    launch: "var(--cat-launch)",
    spaceweather: "var(--cat-spaceweather)",
    asteroid: "var(--cat-asteroid)",
    mission: "var(--cat-mission)",
  };
  const CATEGORY_ICONS = {
    sky: "✨", launch: "🚀", spaceweather: "🌌", asteroid: "☄️", mission: "🛰️",
  };
  const MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia"];
  const MONTHS_SHORT = ["sty", "lut", "mar", "kwi", "maj", "cze",
    "lip", "sie", "wrz", "paź", "lis", "gru"];
  const MONTHS_NOM = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"];

  const el = (id) => document.getElementById(id);
  const state = { events: [], categories: {}, active: new Set(), query: "", onlyBig: false, showPast: false };

  /* --- pomocnicze ------------------------------------------------------- */

  const parse = (iso) => new Date(iso);

  function formatDate(d) {
    return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ` +
      `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }

  /** Odliczanie w formie zdania - "za 3 dni", "za 4 godziny", "wczoraj". */
  function relative(d, now) {
    const diff = d - now;
    const abs = Math.abs(diff);
    const day = 86400000;
    const plural = (n, one, few, many) => {
      const t = n % 10, h = n % 100;
      if (n === 1) return one;
      if (t >= 2 && t <= 4 && (h < 10 || h >= 20)) return few;
      return many;
    };
    let n, unit;
    if (abs < 3600000) { n = Math.max(1, Math.round(abs / 60000)); unit = plural(n, "minutę", "minuty", "minut"); }
    else if (abs < day) { n = Math.round(abs / 3600000); unit = plural(n, "godzinę", "godziny", "godzin"); }
    else if (abs < 60 * day) { n = Math.round(abs / day); unit = plural(n, "dzień", "dni", "dni"); }
    else { n = Math.round(abs / (30.44 * day)); unit = plural(n, "miesiąc", "miesiące", "miesięcy"); }
    return diff >= 0 ? `za ${n} ${unit}` : `${n} ${unit} temu`;
  }

  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* --- render ----------------------------------------------------------- */

  function eventCard(ev, now) {
    const d = parse(ev.starts_at);
    const past = d < now;
    const stars = "★".repeat(ev.importance) + "☆".repeat(5 - ev.importance);
    const isNew = ev.added_on === state.today && !past;

    const badges = [
      `<span class="badge">${CATEGORY_ICONS[ev.category] || "•"} ${escapeHtml(state.categories[ev.category] || ev.category)}</span>`,
      isNew ? '<span class="badge new">nowy wpis</span>' : "",
      ev.rescheduled_from ? '<span class="badge moved">termin przesunięty</span>' : "",
      `<span class="stars" title="Ocena atrakcyjności: ${ev.importance}/5">${stars}</span>`,
      past ? "" : `<span class="countdown-inline">${relative(d, now)}</span>`,
    ].join("");

    const tags = (ev.tags || []).slice(0, 4)
      .map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("");
    const links = (ev.links || [])
      .map((l) => `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${escapeHtml(l.label)}</a>`).join("");
    const place = ev.location ? `<span class="tag">📍 ${escapeHtml(ev.location)}</span>` : "";

    return `<article class="event${past ? " past" : ""}" id="${escapeHtml(ev.id)}" style="--cat:${CATEGORY_COLORS[ev.category] || "var(--accent)"}">
      <div class="date-badge">
        <span class="day">${d.getDate()}</span>
        <span class="mon">${MONTHS_SHORT[d.getMonth()]}</span>
        <span class="time">${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}</span>
      </div>
      <div>
        <h3>${escapeHtml(ev.title)}</h3>
        <div class="meta">${badges}</div>
        <p>${escapeHtml(ev.summary)}</p>
        <div class="meta">${tags}${place}</div>
        <div class="links">${links}</div>
      </div>
    </article>`;
  }

  /** @param ignoreCategory - do liczenia etykiet przy filtrach kategorii */
  function matches(ev, now, ignoreCategory) {
    if (!state.showPast && parse(ev.starts_at) < now - 6 * 3600000) return false;
    if (state.onlyBig && ev.importance < 4) return false;
    if (!ignoreCategory && state.active.size && !state.active.has(ev.category)) return false;
    if (state.query) {
      const hay = `${ev.title} ${ev.summary} ${(ev.tags || []).join(" ")} ${ev.location || ""}`.toLowerCase();
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

  function render() {
    const now = new Date();
    const visible = state.events.filter((ev) => matches(ev, now, false));
    updateCounts(now);
    el("empty").hidden = visible.length > 0;

    let html = "";
    let currentMonth = "";
    for (const ev of visible) {
      const d = parse(ev.starts_at);
      const key = `${MONTHS_NOM[d.getMonth()]} ${d.getFullYear()}`;
      if (key !== currentMonth) {
        currentMonth = key;
        html += `<h2 class="month">${key}</h2>`;
      }
      html += eventCard(ev, now);
    }
    el("timeline").innerHTML = html;
    el("status").hidden = true;
  }

  function renderFilters() {
    el("filters").innerHTML = Object.entries(state.categories)
      .map(([key, label]) =>
        `<button class="chip" data-cat="${key}" aria-pressed="false">
           ${CATEGORY_ICONS[key] || "•"} ${escapeHtml(label)}<span class="count">0</span>
         </button>`).join("");

    el("filters").addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      const cat = chip.dataset.cat;
      const on = !state.active.has(cat);
      on ? state.active.add(cat) : state.active.delete(cat);
      chip.setAttribute("aria-pressed", String(on));
      render();
    });
  }

  function renderHero(doc) {
    const now = new Date();
    const next = state.events
      .filter((ev) => parse(ev.starts_at) > now && ev.importance >= 4)
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0];
    if (!next) return;

    el("hero").hidden = false;
    el("hero-title").textContent = next.title;
    el("hero-when").textContent = formatDate(parse(next.starts_at)) +
      (next.location ? ` · ${next.location}` : "");
    el("hero-summary").textContent = next.summary;
    el("hero-links").innerHTML = (next.links || [])
      .map((l) => `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${escapeHtml(l.label)}</a>`).join("");

    const target = parse(next.starts_at);
    const tick = () => {
      let left = Math.max(0, target - new Date());
      const days = Math.floor(left / 86400000); left -= days * 86400000;
      const hrs = Math.floor(left / 3600000); left -= hrs * 3600000;
      const mins = Math.floor(left / 60000);
      const secs = Math.floor((left - mins * 60000) / 1000);
      el("hero-countdown").innerHTML = [[days, "dni"], [hrs, "godz."], [mins, "min"], [secs, "sek."]]
        .map(([v, l]) => `<span><b>${String(v).padStart(2, "0")}</b><small>${l}</small></span>`).join("");
    };
    tick();
    setInterval(tick, 1000);

    const pic = doc.apod;
    if (pic && pic.image) {
      el("apod").hidden = false;
      el("apod-img").src = pic.image;
      el("apod-img").alt = pic.title || "Astronomiczne zdjęcie dnia";
      el("apod-link").href = pic.hdimage || pic.link;
      el("apod-title").textContent = pic.title || "";
      el("apod-credit").textContent = `${pic.credit || "NASA"} · ${pic.date || ""}`;
    }
  }

  function renderSources(doc) {
    const labels = { ok: "działa", error: "chwilowo niedostępne", skipped: "pominięte" };
    el("sources").innerHTML = (doc.sources || []).map((s) =>
      `<li><span class="dot ${s.status}"></span><span>${escapeHtml(s.name)} –
        ${labels[s.status] || s.status}${s.count ? ` (${s.count})` : ""}</span></li>`).join("");
  }

  /* --- start ------------------------------------------------------------ */

  function bind() {
    let timer;
    el("search").addEventListener("input", (e) => {
      clearTimeout(timer);
      timer = setTimeout(() => { state.query = e.target.value.trim().toLowerCase(); render(); }, 150);
    });
    el("only-big").addEventListener("change", (e) => { state.onlyBig = e.target.checked; render(); });
    el("show-past").addEventListener("change", (e) => { state.showPast = e.target.checked; render(); });
  }

  async function init() {
    el("tz").textContent = Intl.DateTimeFormat().resolvedOptions().timeZone || "czas lokalny";
    try {
      const res = await fetch(`data/events.json?v=${Date.now()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const doc = await res.json();

      state.events = doc.events || [];
      state.categories = doc.categories || {};
      state.today = new Date().toISOString().slice(0, 10);

      const gen = parse(doc.generated_at);
      el("generated").textContent = `${formatDate(gen)} (${relative(gen, new Date())})`;
      el("generated").dateTime = doc.generated_at;

      renderFilters();
      renderHero(doc);
      renderSources(doc);
      bind();
      render();

      if (location.hash) {
        const target = document.getElementById(location.hash.slice(1));
        if (target) target.scrollIntoView();
      }
    } catch (err) {
      el("status").innerHTML = `Nie udało się wczytać danych (${escapeHtml(err.message)}).
        Jeśli otwierasz plik lokalnie, uruchom serwer: <code>python3 -m http.server</code>.`;
    }
  }

  init();
})();
