import json
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
        for element_id in {"edition-meta", "edition-select", "topic-filters", "lead-story", "story-stream"}:
            self.assertIn(element_id, self.inspector.ids)
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

    def test_explore_headline_uses_restrained_full_measure(self):
        self.assertIn("max-width: 100%", self.css)
        self.assertIn("text-wrap: balance", self.css)
        self.assertIn("font-size: clamp(1.95rem, 3vw, 3.5rem)", self.css)
        self.assertIn("line-height: 0.98", self.css)
        self.assertNotIn("max-width: 20ch", self.css)

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
        self.assertIn("column-rule", self.css)
        self.assertIn("border-block", self.css)


if __name__ == "__main__":
    unittest.main()
