import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / "scripts" / "build.py"


def load_build_module():
    spec = importlib.util.spec_from_file_location("newspaper_build", BUILD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_payload():
    return {
        "schema_version": 1,
        "edition": {
            "date": "2026-09-03",
            "title": "The Daily Signal",
            "kicker": "A demo edition",
            "status": "demo",
            "updated_at": "2026-09-03T06:30:00+03:00",
        },
        "sections": ["Bitcoin", "AI", "Robotics", "Longevity"],
        "lead_story_id": "story-1",
        "stories": [
            {
                "id": "story-1",
                "section": "Bitcoin",
                "rank": 1,
                "story_type": "Briefing",
                "title": "A clearly marked demonstration story",
                "summary": "This is sample copy used to exercise the newspaper layout.",
                "source": {"name": "Demo desk", "url": "https://example.com/source"},
                "canonical_url": "https://example.com/story",
                "published_at": "2026-09-03T05:00:00+03:00",
                "corroboration": [
                    {"name": "Sample source", "url": "https://example.org/context"}
                ],
                "quality": {
                    "signal": "developing",
                    "confidence": "medium",
                    "note": "Demonstration value; not a live editorial assessment.",
                },
                "tags": ["Demo"],
            }
        ],
    }


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = load_build_module()

    def test_accepts_complete_document(self):
        self.assertEqual(self.build.validate_news(valid_payload()), [])

    def test_rejects_missing_required_story_fields(self):
        payload = valid_payload()
        del payload["stories"][0]["summary"]
        errors = self.build.validate_news(payload)
        self.assertTrue(any("summary" in error for error in errors), errors)

    def test_rejects_duplicate_ids_unknown_sections_and_bad_urls(self):
        payload = valid_payload()
        duplicate = dict(payload["stories"][0])
        duplicate["section"] = "Markets"
        duplicate["canonical_url"] = "javascript:alert(1)"
        payload["stories"].append(duplicate)
        errors = self.build.validate_news(payload)
        joined = "\n".join(errors)
        self.assertIn("duplicate", joined)
        self.assertIn("section", joined)
        self.assertIn("https", joined)

    def test_rejects_invalid_lead_and_timestamp(self):
        payload = valid_payload()
        payload["lead_story_id"] = "missing"
        payload["edition"]["updated_at"] = "this morning"
        errors = "\n".join(self.build.validate_news(payload))
        self.assertIn("lead_story_id", errors)
        self.assertIn("updated_at", errors)

    def test_production_validation_rejects_a_thin_live_edition(self):
        payload = valid_payload()
        payload["edition"]["status"] = "live"
        errors = self.build.validate_production_coverage(payload)
        self.assertIn("live editions need at least 12 stories; found 1", errors)

    def test_production_validate_command_rejects_a_thin_live_file(self):
        payload = valid_payload()
        payload["edition"]["status"] = "live"
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate.json"
            candidate.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                self.build.main(["validate", "--production", str(candidate)]),
                2,
            )

    def test_rejects_undeclared_fields_to_catch_feed_drift(self):
        payload = valid_payload()
        payload["engagement_score"] = 99
        payload["stories"][0]["clicks"] = 1000
        errors = "\n".join(self.build.validate_news(payload))
        self.assertIn("engagement_score", errors)
        self.assertIn("clicks", errors)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = load_build_module()

    def test_invalid_ingest_never_replaces_current_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            target = folder / "news.json"
            candidate = folder / "candidate.json"
            target.write_text('{"current": true}\n', encoding="utf-8")
            candidate.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(self.build.ValidationError):
                self.build.atomic_ingest(candidate, target)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"current": true}\n')

    def test_valid_ingest_atomically_replaces_and_normalizes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            target = folder / "data" / "news.json"
            candidate = folder / "candidate.json"
            candidate.write_text(json.dumps(valid_payload()), encoding="utf-8")
            self.build.atomic_ingest(candidate, target)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), valid_payload())
            self.assertTrue(target.read_text(encoding="utf-8").endswith("\n"))

    def test_new_day_ingest_archives_previous_edition_and_writes_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            target = folder / "data" / "news.json"
            target.parent.mkdir(parents=True)
            previous = valid_payload()
            target.write_text(json.dumps(previous), encoding="utf-8")
            candidate_payload = valid_payload()
            candidate_payload["edition"] = dict(candidate_payload["edition"])
            candidate_payload["edition"]["date"] = "2026-09-04"
            candidate_payload["edition"]["updated_at"] = "2026-09-04T08:00:00+03:00"
            candidate = folder / "candidate.json"
            candidate.write_text(json.dumps(candidate_payload), encoding="utf-8")

            self.build.atomic_ingest(candidate, target)

            archived = target.parent / "archive" / "2026-09-03.json"
            index = json.loads((target.parent / "archive.json").read_text())
            self.assertEqual(json.loads(archived.read_text()), previous)
            self.assertEqual(
                index["editions"],
                [
                    {"date": "2026-09-04", "url": "./data/news.json", "current": True},
                    {"date": "2026-09-03", "url": "./data/archive/2026-09-03.json", "current": False},
                ],
            )

    def test_same_day_ingest_refreshes_index_without_archiving_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            target = folder / "data" / "news.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(valid_payload()), encoding="utf-8")
            candidate = folder / "candidate.json"
            candidate.write_text(json.dumps(valid_payload()), encoding="utf-8")

            self.build.atomic_ingest(candidate, target)

            self.assertFalse((target.parent / "archive" / "2026-09-03.json").exists())
            index = json.loads((target.parent / "archive.json").read_text())
            self.assertEqual(index["editions"], [
                {"date": "2026-09-03", "url": "./data/news.json", "current": True}
            ])

    def test_build_validates_then_copies_static_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "public"
            output = folder / "dist"
            (source / "data").mkdir(parents=True)
            (source / "index.html").write_text("<!doctype html>", encoding="utf-8")
            (source / "data" / "news.json").write_text(
                json.dumps(valid_payload()), encoding="utf-8"
            )
            self.build.build_site(source, output)
            self.assertEqual((output / "index.html").read_text(), "<!doctype html>")
            self.assertEqual(
                json.loads((output / "data" / "news.json").read_text()), valid_payload()
            )

    def test_failed_build_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "public"
            output = folder / "dist"
            (source / "data").mkdir(parents=True)
            output.mkdir()
            (output / "sentinel.txt").write_text("keep", encoding="utf-8")
            (source / "data" / "news.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(self.build.ValidationError):
                self.build.build_site(source, output)
            self.assertEqual((output / "sentinel.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
