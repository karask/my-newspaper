(function () {
  "use strict";

  var core = window.NewsCore;
  var state = { edition: null, topic: "All", editionUrl: "./data/news.json" };
  var elements = {
    meta: document.getElementById("edition-meta"),
    filters: document.getElementById("topic-filters"),
    grid: document.getElementById("story-grid"),
    status: document.getElementById("page-status"),
    themeToggle: document.getElementById("theme-toggle"),
    themeLabel: document.getElementById("theme-label"),
    editionSelect: document.getElementById("edition-select"),
  };

  function formatDate(value, options) {
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Time unavailable";
    return new Intl.DateTimeFormat(undefined, options).format(date);
  }

  function fullTimestamp(value) {
    return formatDate(value, { dateStyle: "long", timeStyle: "short" });
  }

  function shortTimestamp(value) {
    return formatDate(value, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function setBusy(isBusy) {
    elements.grid.setAttribute("aria-busy", String(isBusy));
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    var nextLabel = theme === "dark" ? "light" : "dark";
    elements.themeLabel.textContent = nextLabel;
    elements.themeToggle.setAttribute("aria-label", "Switch to " + nextLabel + " surface");
    document.querySelector('meta[name="theme-color"]').setAttribute(
      "content",
      theme === "dark" ? "#161310" : "#efe8dc"
    );
  }

  elements.themeToggle.addEventListener("click", function () {
    var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      localStorage.setItem("daily-signal-theme", next);
    } catch (_) {
      // Preference persistence is optional; the theme still changes for this visit.
    }
  });

  function safeEditionUrl(value) {
    var url = String(value || "");
    return url === "./data/news.json" || /^\.\/data\/archive\/\d{4}-\d{2}-\d{2}\.json$/.test(url)
      ? url
      : "./data/news.json";
  }

  function renderEditionOptions(index) {
    var editions = index && Array.isArray(index.editions) ? index.editions : [];
    if (!editions.length) return;
    elements.editionSelect.innerHTML = editions.map(function (item) {
      var url = safeEditionUrl(item.url);
      var label = formatDate(item.date + "T12:00:00", {
        year: "numeric", month: "long", day: "numeric"
      }) + (item.current ? " — Current" : "");
      return '<option value="' + core.escapeHtml(url) + '">' + core.escapeHtml(label) + "</option>";
    }).join("");
    elements.editionSelect.value = state.editionUrl;
  }

  async function loadArchiveIndex() {
    try {
      var response = await fetch("./data/archive.json", { cache: "no-store" });
      if (!response.ok) return;
      renderEditionOptions(await response.json());
    } catch (_) {
      // The current edition remains readable when no archive has been published yet.
    }
  }

  elements.editionSelect.addEventListener("change", function () {
    var option = elements.editionSelect.options[elements.editionSelect.selectedIndex];
    loadEdition(option.value);
  });

  var badgeClasses = { section: "badge--section", type: "badge--type" };

  function badge(label, modifier) {
    return '<span class="badge ' + core.escapeHtml(badgeClasses[modifier] || "badge--plain") + '">' +
      core.escapeHtml(label) + "</span>";
  }

  function qualityMarkup(story) {
    var quality = story.quality || {};
    var confidence = quality.confidence || "unknown";
    var signal = quality.signal || "unrated";
    return '<span class="quality quality--' + core.escapeHtml(confidence) + '" title="' +
      core.escapeHtml(quality.note || "No editorial note supplied") + '">' +
      '<span class="quality-dot" aria-hidden="true"></span>' +
      core.escapeHtml(signal) + " · " + core.escapeHtml(confidence) + " confidence</span>";
  }

  function popularityMarkup(story) {
    var popularity = story.popularity;
    if (!popularity || !popularity.label) return "";
    return '<span class="popularity" title="Observed ' +
      core.escapeHtml(fullTimestamp(popularity.observed_at)) + '">' +
      core.escapeHtml(popularity.label) + "</span>";
  }

  function evidenceMarkup(story) {
    return '<div class="evidence-line">' + qualityMarkup(story) +
      popularityMarkup(story) + "</div>";
  }

  function sourceLinksMarkup(story) {
    return '<div class="source-list" aria-label="Story sources"><span class="source-label">sources</span>' +
      core.storyLinks(story).map(function (link) {
        return '<a class="source-link badge badge--source" href="' +
          core.escapeHtml(link.url) + '" target="_blank" rel="noopener noreferrer">' +
          core.escapeHtml(link.name) + " ↗</a>";
      }).join("") + "</div>";
  }

  function storyTime(story) {
    return '<time datetime="' + core.escapeHtml(story.published_at || "") + '" title="' +
      core.escapeHtml(fullTimestamp(story.published_at)) + '">' +
      core.escapeHtml(shortTimestamp(story.published_at)) + "</time>";
  }

  function renderMeta() {
    var edition = state.edition.edition || {};
    var storyCount = Array.isArray(state.edition.stories) ? state.edition.stories.length : 0;
    var status = edition.status || "unknown";
    var extra = status === "demo" ? '<span class="demo-stamp">demo</span>' :
      (state.editionUrl !== "./data/news.json" ? '<span class="demo-stamp">archive</span>' : "");
    elements.meta.innerHTML = '<span class="edition-date">' +
      core.escapeHtml(formatDate(edition.date + "T12:00:00", { weekday: "long", year: "numeric", month: "long", day: "numeric" })) +
      '</span><span class="edition-kicker">' + core.escapeHtml(edition.kicker || "Daily briefing") +
      '</span><span class="meta-count">stories ' + core.escapeHtml(String(storyCount)) +
      '</span><span class="edition-updated">upd <time datetime="' + core.escapeHtml(edition.updated_at || "") + '">' +
      core.escapeHtml(shortTimestamp(edition.updated_at)) +
      '</time></span><span class="meta-status">status ' + core.escapeHtml(status) + "</span>" + extra;
  }

  function renderFilters() {
    var topics = ["All"].concat(Array.isArray(state.edition.sections) ? state.edition.sections : []);
    elements.filters.innerHTML = topics.map(function (topic) {
      var selected = topic === state.topic;
      return '<button type="button" class="topic-filter" data-topic="' + core.escapeHtml(topic) +
        '" aria-pressed="' + String(selected) + '">' + core.escapeHtml(topic) + "</button>";
    }).join("");
    elements.filters.querySelectorAll("button").forEach(function (button) {
      button.addEventListener("click", function () {
        state.topic = button.dataset.topic;
        render();
      });
    });
  }

  function renderStories(stories) {
    if (!stories.length) {
      elements.grid.innerHTML = statePanel("empty");
      return;
    }
    elements.grid.innerHTML = stories.map(function (story, index) {
      var url = core.safeUrl(story.canonical_url);
      return '<article class="story-card">' +
        '<div class="story-card__top"><p class="story-rank" aria-label="Position ' +
        core.escapeHtml(String(index + 1)) + '">' +
        core.escapeHtml(String(index + 1).padStart(2, "0")) + "</p>" +
        '<div class="story-taxonomy">' + badge(story.section || "Unfiled", "section") +
        badge(story.story_type || "Story", "type") + storyTime(story) + "</div></div>" +
        '<h3><a href="' + core.escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' +
        core.escapeHtml(story.title || "Untitled story") + "</a></h3>" +
        '<p class="story-summary">' + core.escapeHtml(story.summary || "No summary was supplied.") + "</p>" +
        evidenceMarkup(story) + sourceLinksMarkup(story) + "</article>";
    }).join("");
  }

  function statePanel(kind) {
    var heading = kind === "error" ? "Load failed" : "Empty section";
    var action = kind === "error" ? '<button type="button" class="retry-button" id="retry-load">Try again</button>' : "";
    return '<div class="state-panel"><p class="state-eyebrow">' +
      (kind === "error" ? "Edition unavailable" : "Nothing filed") + '</p><h3>' + heading +
      '</h3><p>' + core.stateMessage(kind) + "</p>" + action + "</div>";
  }

  function render() {
    var stories = core.selectStories(state.edition.stories, state.topic);
    renderMeta();
    renderFilters();
    renderStories(stories);
    elements.status.textContent = stories.length ?
      (state.topic === "All" ? "Full edition loaded." : state.topic + " section loaded.") :
      core.stateMessage('empty');
    elements.status.classList.add("visually-hidden");
    setBusy(false);
  }

  function showError() {
    elements.grid.innerHTML = statePanel("error");
    elements.filters.innerHTML = "";
    elements.meta.textContent = "Edition unavailable";
    elements.status.textContent = core.stateMessage('error');
    elements.status.classList.remove("visually-hidden");
    setBusy(false);
    var retry = document.getElementById("retry-load");
    if (retry) retry.addEventListener("click", function () { loadEdition(state.editionUrl); });
  }

  async function loadEdition(url) {
    var requestedUrl = safeEditionUrl(url || "./data/news.json");
    setBusy(true);
    elements.status.classList.remove("visually-hidden");
    elements.status.textContent = "Opening the edition…";
    try {
      var response = await fetch(requestedUrl, { cache: "no-store" });
      if (!response.ok) throw new Error("Edition request failed with " + response.status);
      var document = await response.json();
      if (!document || !Array.isArray(document.stories)) throw new Error("Edition data is malformed");
      state.edition = document;
      state.editionUrl = requestedUrl;
      state.topic = "All";
      render();
      elements.editionSelect.value = requestedUrl;
    } catch (error) {
      console.error("Unable to load the daily edition", error);
      showError();
    }
  }

  setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  loadArchiveIndex();
  loadEdition();
})();
