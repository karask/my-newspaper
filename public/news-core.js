(function (root) {
  "use strict";

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (character) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[character];
    });
  }

  function safeUrl(value) {
    try {
      var parsed = new URL(String(value));
      return parsed.protocol === "https:" ? parsed.href : "#";
    } catch (_) {
      return "#";
    }
  }

  function selectStories(stories, topic) {
    if (!Array.isArray(stories)) return [];
    return stories
      .filter(function (story) {
        return story && typeof story === "object" && (topic === "All" || story.section === topic);
      })
      .map(function (story, index) {
        return { story: story, index: index };
      })
      .sort(function (left, right) {
        var leftPopularity = left.story.popularity && Number.isInteger(left.story.popularity.engagement)
          ? left.story.popularity.engagement : -1;
        var rightPopularity = right.story.popularity && Number.isInteger(right.story.popularity.engagement)
          ? right.story.popularity.engagement : -1;
        var leftRank = Number.isInteger(left.story.rank) ? left.story.rank : Number.MAX_SAFE_INTEGER;
        var rightRank = Number.isInteger(right.story.rank) ? right.story.rank : Number.MAX_SAFE_INTEGER;
        return rightPopularity - leftPopularity || leftRank - rightRank || left.index - right.index;
      })
      .map(function (entry) {
        return entry.story;
      });
  }

  function leadFor(document, topic) {
    var ranked = selectStories(document && document.stories, topic);
    if (!ranked.length) return null;
    if (topic !== "All") return ranked[0];
    return ranked.find(function (story) {
      return story.id === document.lead_story_id;
    }) || ranked[0];
  }

  function storyLinks(story) {
    var links = [];
    var seen = Object.create(null);
    function add(name, url) {
      var safe = safeUrl(url);
      if (safe === "#" || seen[safe]) return;
      seen[safe] = true;
      links.push({ name: String(name || "Source"), url: safe });
    }
    var source = story && story.source || {};
    add(source.name, source.url);
    add("Canonical", story && story.canonical_url);
    (story && Array.isArray(story.corroboration) ? story.corroboration : []).forEach(function (link) {
      add(link && link.name, link && link.url);
    });
    return links;
  }

  function sourceCountLabel(corroboration) {
    var count = 1 + (Array.isArray(corroboration) ? corroboration.length : 0);
    return count + (count === 1 ? " source" : " sources");
  }

  function stateMessage(kind) {
    if (kind === "empty") return "No stories are filed in this section yet.";
    if (kind === "error") return "The edition could not be opened. Try again in a moment.";
    return "Opening the edition…";
  }

  root.NewsCore = Object.freeze({
    escapeHtml: escapeHtml,
    safeUrl: safeUrl,
    selectStories: selectStories,
    leadFor: leadFor,
    storyLinks: storyLinks,
    sourceCountLabel: sourceCountLabel,
    stateMessage: stateMessage,
  });
})(typeof window === "undefined" ? globalThis : window);
