(function () {
  "use strict";

  var core = window.NewsCore;
  var state = { edition: null, topic: "All", editionUrl: "./data/news.json" };
  var elements = {
    meta: document.getElementById("edition-meta"),
    filters: document.getElementById("topic-filters"),
    lead: document.getElementById("lead-story"),
    stream: document.getElementById("story-stream"),
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
    elements.lead.setAttribute("aria-busy", String(isBusy));
    elements.stream.setAttribute("aria-busy", String(isBusy));
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    var nextLabel = theme === "dark" ? "Light edition" : "Dark edition";
    elements.themeLabel.textContent = nextLabel;
    elements.themeToggle.setAttribute("aria-label", "Switch to " + nextLabel.toLowerCase());
    document.querySelector('meta[name="theme-color"]').setAttribute(
      "content",
      theme === "dark" ? "#171613" : "#eee7d9"
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

  function evidenceMarkup(story) {
    var source = story.source || {};
    var sourceUrl = core.safeUrl(source.url);
    return '<div class="evidence-line">' +
      '<a class="source-link badge badge--source" href="' + core.escapeHtml(sourceUrl) +
      '" target="_blank" rel="noopener noreferrer">' + core.escapeHtml(source.name || "Unknown source") + "</a>" +
      '<span aria-hidden="true">/</span>' +
      '<span>' + core.escapeHtml(core.sourceCountLabel(story.corroboration)) + "</span>" +
      '<span aria-hidden="true">/</span>' + qualityMarkup(story) + "</div>";
  }

  function storyTime(story) {
    return '<time datetime="' + core.escapeHtml(story.published_at || "") + '" title="' +
      core.escapeHtml(fullTimestamp(story.published_at)) + '">' +
      core.escapeHtml(shortTimestamp(story.published_at)) + "</time>";
  }

  function renderMeta() {
    var edition = state.edition.edition || {};
    var status = edition.status === "demo" ? '<span class="demo-stamp">Demo edition</span>' :
      (state.editionUrl !== "./data/news.json" ? '<span class="demo-stamp">Archive edition</span>' : "");
    elements.meta.innerHTML = '<span class="edition-date">' +
      core.escapeHtml(formatDate(edition.date + "T12:00:00", { weekday: "long", year: "numeric", month: "long", day: "numeric" })) +
      '</span><span class="edition-kicker">' + core.escapeHtml(edition.kicker || "Daily briefing") +
      '</span><span class="edition-updated">Updated <time datetime="' + core.escapeHtml(edition.updated_at || "") + '">' +
      core.escapeHtml(shortTimestamp(edition.updated_at)) + "</time></span>" + status;
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

  function renderLead(story) {
    if (!story) {
      elements.lead.innerHTML = statePanel("empty");
      return;
    }
    var url = core.safeUrl(story.canonical_url);
    elements.lead.innerHTML = '<article class="lead-article">' +
      '<div class="story-taxonomy">' + badge(story.section || "Unfiled", "section") +
      badge(story.story_type || "Story", "type") + storyTime(story) + "</div>" +
      '<h3><a href="' + core.escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' +
      core.escapeHtml(story.title || "Untitled story") + "</a></h3>" +
      '<p class="lead-summary">' + core.escapeHtml(story.summary || "No summary was supplied.") + "</p>" +
      evidenceMarkup(story) +
      '<a class="read-link" href="' + core.escapeHtml(url) +
      '" target="_blank" rel="noopener noreferrer">Read the canonical story <span aria-hidden="true">↗</span></a>' +
      "</article>";
  }

  function renderStream(stories, lead) {
    var remainder = stories.filter(function (story) { return !lead || story.id !== lead.id; });
    if (!remainder.length) {
      elements.stream.innerHTML = statePanel("empty");
      return;
    }
    elements.stream.innerHTML = remainder.map(function (story) {
      var url = core.safeUrl(story.canonical_url);
      return '<article class="stream-story">' +
        '<p class="story-rank" aria-label="Rank ' + core.escapeHtml(story.rank || "—") + '">' +
        core.escapeHtml(String(story.rank || "—").padStart(2, "0")) + "</p>" +
        '<div class="stream-copy"><div class="story-taxonomy">' +
        badge(story.section || "Unfiled", "section") + badge(story.story_type || "Story", "type") +
        storyTime(story) + "</div>" +
        '<h3><a href="' + core.escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' +
        core.escapeHtml(story.title || "Untitled story") + "</a></h3>" +
        '<p class="stream-summary">' + core.escapeHtml(story.summary || "No summary was supplied.") + "</p>" +
        evidenceMarkup(story) + "</div></article>";
    }).join("");
  }

  function statePanel(kind) {
    var heading = kind === "error" ? "The presses paused" : "A quiet desk";
    var action = kind === "error" ? '<button type="button" class="retry-button" id="retry-load">Try again</button>' : "";
    return '<div class="state-panel"><p class="state-eyebrow">' +
      (kind === "error" ? "Edition unavailable" : "Nothing filed") + '</p><h3>' + heading +
      '</h3><p>' + core.stateMessage(kind) + "</p>" + action + "</div>";
  }

  function render() {
    var stories = core.selectStories(state.edition.stories, state.topic);
    var lead = core.leadFor(state.edition, state.topic);
    renderMeta();
    renderFilters();
    renderLead(lead);
    renderStream(stories, lead);
    elements.status.textContent = stories.length ?
      (state.topic === "All" ? "Full edition loaded." : state.topic + " section loaded.") :
      core.stateMessage('empty');
    elements.status.classList.add("visually-hidden");
    setBusy(false);
  }

  function showError() {
    elements.lead.innerHTML = statePanel("error");
    elements.stream.innerHTML = "";
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
