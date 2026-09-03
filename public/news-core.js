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
        var leftRank = Number.isInteger(left.story.rank) ? left.story.rank : Number.MAX_SAFE_INTEGER;
        var rightRank = Number.isInteger(right.story.rank) ? right.story.rank : Number.MAX_SAFE_INTEGER;
        return leftRank - rightRank || left.index - right.index;
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
    sourceCountLabel: sourceCountLabel,
    stateMessage: stateMessage,
  });
})(typeof window === "undefined" ? globalThis : window);
