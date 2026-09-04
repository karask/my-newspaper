import ast
import json
import unittest
from pathlib import Path

from tests.test_build import load_build_module


ROOT = Path(__file__).resolve().parents[1]


class PublishedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "docs" / "news.schema.json").read_text())
        cls.example = json.loads((ROOT / "docs" / "news.example.json").read_text())
        cls.seed = json.loads((ROOT / "public" / "data" / "news.json").read_text())
        cls.build = load_build_module()

    def test_schema_is_documented_strict_and_versioned(self):
        self.assertEqual(
            self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], 1)
        self.assertFalse(self.schema["additionalProperties"])
        self.assertFalse(self.schema["$defs"]["story"]["additionalProperties"])
        self.assertEqual(
            self.schema["properties"]["sections"]["prefixItems"],
            [{"const": "Bitcoin"}, {"const": "AI"}, {"const": "Robotics"}, {"const": "Longevity"}],
        )

    def test_example_and_seed_pass_the_runtime_validator(self):
        self.assertEqual(self.build.validate_news(self.example), [])
        self.assertEqual(self.build.validate_news(self.seed), [])

    def test_seed_is_honest_about_demo_or_live_content(self):
        self.assertIn(self.seed["edition"]["status"], {"demo", "live"})
        self.assertEqual(
            {story["section"] for story in self.seed["stories"]}, set(self.seed["sections"])
        )
        for story in self.seed["stories"]:
            if self.seed["edition"]["status"] == "demo":
                self.assertTrue(story["title"].startswith("DEMO —"), story["title"])
                self.assertIn("Demo", story["tags"])
                self.assertIn("Demonstration", story["quality"]["note"])
            else:
                self.assertFalse(story["title"].startswith("DEMO —"), story["title"])
                self.assertNotIn("Demo", story["tags"])
                self.assertNotIn("example.com", story["canonical_url"])

    def test_feed_contains_no_engagement_or_invented_performance_metrics(self):
        forbidden = {"views", "likes", "shares", "clicks", "score", "read_time", "trending"}
        for story in self.seed["stories"]:
            self.assertTrue(forbidden.isdisjoint(story.keys()))

    def test_generator_imports_only_the_standard_library(self):
        tree = ast.parse((ROOT / "scripts" / "build.py").read_text())
        imports = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        } | {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        allowed = {
            "__future__", "argparse", "json", "os", "shutil", "sys", "tempfile",
            "datetime", "pathlib", "typing", "urllib"
        }
        self.assertTrue(imports <= allowed, imports - allowed)


class EditorialAutomationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prompt = (ROOT / "cron-prompt.md").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(
            encoding="utf-8"
        )

    def test_pages_deploy_enforces_production_coverage(self):
        self.assertIn(
            "python scripts/build.py validate --production public/data/news.json",
            self.workflow,
        )

    def test_pipeline_has_an_official_x_release_sweep(self):
        for token in [
            "OFFICIAL X RELEASE SWEEP",
            "grok --no-auto-update -p",
            "@OpenAI",
            "@claudeai",
            "@GoogleDeepMind",
            "@Figure_robot",
            "@Nature",
            "official account is sufficient primary evidence",
        ]:
            self.assertIn(token, self.prompt)

    def test_pipeline_has_broad_coverage_and_catchup_gates(self):
        for token in [
            "16–30 stories total",
            "4–8 qualifying stories per topic",
            "minimum of 12",
            "72-hour catch-up sweep",
            "second gap-filling sweep",
            "already-published canonical URLs",
            "validate --production daily-news-candidate.json",
        ]:
            self.assertIn(token, self.prompt)
        self.assertNotIn("Include 1–3 qualifying stories per topic", self.prompt)


class DocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_has_exact_local_workflow_commands(self):
        for command in [
            "python -m unittest discover -v",
            "python scripts/build.py build",
            "python -m http.server 8000 --directory public",
            "python scripts/build.py validate",
            "python scripts/build.py ingest",
        ]:
            self.assertIn(command, self.readme)

    def test_readme_covers_each_requested_static_host(self):
        for host in ["Cloudflare Pages", "Vercel", "GitHub Pages"]:
            self.assertIn(host, self.readme)

    def test_readme_documents_atomic_contract_and_demo_disclaimer(self):
        self.assertIn("os.replace", self.readme)
        self.assertIn("DEMO", self.readme)
        self.assertIn("not live reporting", self.readme)


if __name__ == "__main__":
    unittest.main()
