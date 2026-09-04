import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


class DocumentInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.landmarks = []
        self.links = []
        self.buttons = []
        self.scripts = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag in {"header", "nav", "main", "footer"}:
            self.landmarks.append((tag, attributes))
        if tag == "a":
            self.links.append(attributes)
        if tag == "button":
            self.buttons.append(attributes)
        if tag == "script" and "src" in attributes:
            self.scripts.append(attributes["src"])

    def handle_data(self, data):
        self.text.append(data)


def run_core(expression):
    if shutil.which("node") is None:
        raise unittest.SkipTest("Node is unavailable for dependency-free JS behavior tests")
    script = f"""
globalThis.window = globalThis;
require({json.dumps(str(PUBLIC / 'news-core.js'))});
const result = {expression};
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script], text=True, capture_output=True, check=True
    )
    return json.loads(completed.stdout)


class SemanticShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        cls.inspector = DocumentInspector()
        cls.inspector.feed(cls.html)

    def test_has_skip_link_and_named_page_landmarks(self):
        self.assertTrue(
            any(link.get("href") == "#main-content" for link in self.inspector.links)
        )
        self.assertIn("main-content", self.inspector.ids)
        tags = [tag for tag, _ in self.inspector.landmarks]
        self.assertIn("header", tags)
        self.assertIn("nav", tags)
        self.assertIn("main", tags)
        self.assertIn("footer", tags)
        self.assertTrue(
            any(attrs.get("aria-label") for tag, attrs in self.inspector.landmarks if tag == "nav")
        )

    def test_has_data_driven_mounts_and_live_status(self):
        for element_id in {"edition-meta", "edition-select", "topic-filters", "story-grid"}:
            self.assertIn(element_id, self.inspector.ids)
        self.assertNotIn("lead-story", self.inspector.ids)
        self.assertNotIn("story-stream", self.inspector.ids)
        self.assertNotIn("explore-heading", self.inspector.ids)
        self.assertNotIn("monitor-heading", self.inspector.ids)
        self.assertIn("page-status", self.inspector.ids)
        self.assertIn('role="status"', self.html)
        self.assertIn('aria-live="polite"', self.html)

    def test_has_accessible_theme_control_and_no_hardcoded_story_copy(self):
        self.assertTrue(
            any(button.get("id") == "theme-toggle" for button in self.inspector.buttons)
        )
        self.assertIn("./news-core.js", self.inspector.scripts)
        self.assertIn("./app.js", self.inspector.scripts)
        self.assertNotIn("A clearly marked demonstration story", self.html)

    def test_dark_mode_is_the_default_without_a_saved_preference(self):
        self.assertIn('saved || "dark"', self.html)
        self.assertNotIn('systemDark ? "dark" : "light"', self.html)


class NewsCoreTests(unittest.TestCase):
    def test_ranked_stream_is_stable_and_filterable(self):
        stories = [
            {"id": "a", "section": "AI", "rank": 2},
            {"id": "b", "section": "Bitcoin", "rank": 1},
            {"id": "c", "section": "AI", "rank": 1},
        ]
        expression = f"NewsCore.selectStories({json.dumps(stories)}, 'AI').map(x => x.id)"
        self.assertEqual(run_core(expression), ["c", "a"])

    def test_popularity_signals_order_the_feed_before_editorial_rank(self):
        stories = [
            {"id": "ranked", "section": "AI", "rank": 1},
            {"id": "popular", "section": "AI", "rank": 8,
             "popularity": {"engagement": 900}},
            {"id": "less-popular", "section": "AI", "rank": 2,
             "popularity": {"engagement": 120}},
        ]
        expression = f"NewsCore.selectStories({json.dumps(stories)}, 'All').map(x => x.id)"
        self.assertEqual(run_core(expression), ["popular", "less-popular", "ranked"])

    def test_lead_uses_declared_story_for_all_and_top_rank_for_topic(self):
        document = {
            "lead_story_id": "b",
            "stories": [
                {"id": "a", "section": "AI", "rank": 1},
                {"id": "b", "section": "Bitcoin", "rank": 2},
                {"id": "c", "section": "Bitcoin", "rank": 1},
            ],
        }
        all_lead = run_core(f"NewsCore.leadFor({json.dumps(document)}, 'All').id")
        topic_lead = run_core(f"NewsCore.leadFor({json.dumps(document)}, 'Bitcoin').id")
        self.assertEqual(all_lead, "b")
        self.assertEqual(topic_lead, "c")

    def test_story_links_include_every_unique_source_and_canonical(self):
        story = {
            "source": {"name": "Official X", "url": "https://x.com/a/status/1"},
            "canonical_url": "https://example.com/release",
            "corroboration": [
                {"name": "Release", "url": "https://example.com/release"},
                {"name": "Reddit", "url": "https://reddit.com/r/a/comments/1"},
            ],
        }
        links = run_core(f"NewsCore.storyLinks({json.dumps(story)})")
        self.assertEqual(
            links,
            [
                {"name": "Official X", "url": "https://x.com/a/status/1"},
                {"name": "Canonical", "url": "https://example.com/release"},
                {"name": "Reddit", "url": "https://reddit.com/r/a/comments/1"},
            ],
        )

    def test_source_count_is_derived_from_corroboration_links(self):
        self.assertEqual(run_core("NewsCore.sourceCountLabel([])"), "1 source")
        self.assertEqual(
            run_core("NewsCore.sourceCountLabel([{name:'a'}, {name:'b'}])"), "3 sources"
        )

    def test_untrusted_text_is_escaped_and_only_https_links_are_allowed(self):
        escaped = run_core("NewsCore.escapeHtml('<img src=x onerror=alert(1)>')")
        self.assertEqual(escaped, "&lt;img src=x onerror=alert(1)&gt;")
        self.assertEqual(run_core("NewsCore.safeUrl('javascript:alert(1)')"), "#")
        self.assertEqual(
            run_core("NewsCore.safeUrl('https://example.com/news')"),
            "https://example.com/news",
        )

    def test_empty_and_error_states_are_specific_and_actionable(self):
        self.assertIn("No stories", run_core("NewsCore.stateMessage('empty')"))
        self.assertIn("Try again", run_core("NewsCore.stateMessage('error')"))


class ClientContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.javascript = (PUBLIC / "app.js").read_text(encoding="utf-8")
        cls.css = (PUBLIC / "styles.css").read_text(encoding="utf-8")

    def test_client_fetches_single_daily_json_without_cache(self):
        self.assertIn("./data/news.json", self.javascript)
        self.assertRegex(self.javascript, r"fetch\([^)]*cache:\s*[\"']no-store[\"']")

    def test_client_supports_filter_theme_error_and_empty_rendering(self):
        for token in ["selectStories", "theme-toggle", "localStorage", "stateMessage('error')", "stateMessage('empty')"]:
            self.assertIn(token, self.javascript)

    def test_client_loads_archive_index_and_switches_editions(self):
        for token in ["./data/archive.json", "edition-select", "loadEdition(option.value)"]:
            self.assertIn(token, self.javascript)

    def test_every_story_uses_one_three_column_card_format(self):
        self.assertIn("renderStories", self.javascript)
        self.assertNotIn("renderLead", self.javascript)
        self.assertNotIn("renderStream", self.javascript)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", self.css)
        self.assertIn(".story-card", self.css)

    def test_source_and_story_type_have_distinct_badge_treatments(self):
        self.assertIn("badge--source", self.javascript)
        self.assertIn("badge--type", self.javascript)
        self.assertIn(".badge--source", self.css)

    def test_styles_include_dark_mode_responsive_focus_and_reduced_motion(self):
        for token in [
            '[data-theme="dark"]',
            "@media (max-width:",
            "@media (prefers-reduced-motion: reduce)",
            ":focus-visible",
            "font-family:",
        ]:
            self.assertIn(token, self.css)

    def test_filters_and_story_stream_are_not_saas_card_grids(self):
        self.assertNotIn("box-shadow:", self.css)
        self.assertNotIn("border-radius: 16px", self.css)
        self.assertNotIn("backdrop-filter", self.css)
        self.assertNotIn("column-count: 2", self.css)
        self.assertIn("grid-template-columns", self.css)
        self.assertIn("border-block", self.css)

    def test_every_story_shows_full_summary_and_all_source_links(self):
        self.assertIn("sourceLinksMarkup", self.javascript)
        self.assertIn("core.storyLinks(story)", self.javascript)
        self.assertIn("class=\"story-summary\"", self.javascript)
        self.assertNotIn("-webkit-line-clamp", self.css)


class TerminalNewswireContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        cls.css = (PUBLIC / "styles.css").read_text(encoding="utf-8")
        cls.javascript = (PUBLIC / "app.js").read_text(encoding="utf-8")

    def test_masthead_is_a_compact_desk_not_a_broadsheet_nameplate(self):
        self.assertIn("desk-bar", self.html)
        self.assertIn("SIGNAL(1)", self.html)
        self.assertNotIn("nameplate-flourish", self.html)
        self.assertNotIn("nameplate", self.html)
        self.assertNotIn("Iowan Old Style", self.css)
        self.assertNotIn("Palatino", self.css)
        self.assertNotIn("::first-letter", self.css)
        self.assertNotIn("8.7rem", self.css)
        self.assertLess(self.html.find("The Daily Signal"), self.html.find("All signals"))
        self.assertIn('id="story-grid"', self.html)
        self.assertNotIn("Explore", self.html)
        self.assertNotIn("Monitor", self.html)

    def test_palette_is_warm_near_black_with_minimal_signal_colors(self):
        self.assertIn("#161310", self.html)
        self.assertIn("#161310", self.css)
        self.assertIn("#161310", self.javascript)
        self.assertIn("#b6e05c", self.css)
        self.assertIn("#5ecad4", self.css)
        self.assertIn("#e3923c", self.css)
        self.assertIn("--mono:", self.css)
        self.assertIn("IBM Plex Mono", self.css)
        self.assertIn("IBM Plex Sans", self.css)

    def test_no_gradients_glass_or_soft_corners(self):
        self.assertNotIn("linear-gradient", self.css)
        self.assertNotIn("radial-gradient", self.css)
        self.assertNotIn("backdrop-filter", self.css)
        self.assertNotIn("filter: blur", self.css)
        radii = re.findall(r"border-radius:\s*([^;]+);", self.css)
        self.assertTrue(radii, "sharp corners should be explicit")
        for value in radii:
            self.assertEqual(value.strip(), "0", value)

    def test_client_presents_real_story_count_update_and_status(self):
        self.assertIn("storyCount", self.javascript)
        self.assertIn("meta-count", self.javascript)
        self.assertIn("meta-status", self.javascript)
        self.assertIn("edition.status", self.javascript)
        self.assertIn("updated_at", self.javascript)
        lowered = self.javascript.lower()
        for token in ("views", "likes", "shares", "trending", "uptime", "dau"):
            self.assertNotIn(token, lowered)

    def test_story_grid_is_dense_and_summaries_stay_readable(self):
        self.assertIn("gap: 1px", self.css)
        self.assertIn("line-height: 1.58", self.css)
        self.assertNotIn("-webkit-line-clamp", self.css)


if __name__ == "__main__":
    unittest.main()
