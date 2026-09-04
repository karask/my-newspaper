#!/usr/bin/env python3
"""Validate, ingest, and build the static Daily Signal newspaper.

This module intentionally uses only the Python standard library so the same
commands work in local development and minimal CI/deployment environments.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "public"
DEFAULT_OUTPUT = ROOT / "dist"
NEWS_FILE = Path("data/news.json")
ARCHIVE_INDEX_FILE = Path("data/archive.json")
SECTIONS = ("Bitcoin", "AI", "Robotics", "Longevity")
CONFIDENCE_LEVELS = {"high", "medium", "low"}
QUALITY_SIGNALS = {"primary", "corroborated", "developing", "analysis"}
ROOT_FIELDS = {"schema_version", "edition", "sections", "lead_story_id", "stories"}
EDITION_FIELDS = {"date", "title", "kicker", "status", "updated_at"}
STORY_FIELDS = {
    "id", "section", "rank", "story_type", "title", "summary", "source",
    "canonical_url", "published_at", "corroboration", "quality", "tags",
}
LINK_FIELDS = {"name", "url"}
QUALITY_FIELDS = {"signal", "confidence", "note"}


class ValidationError(ValueError):
    """Raised when an edition does not satisfy the published data contract."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid news data:\n- " + "\n- ".join(errors))


def _required_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def _required_list(value: Any, path: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return []
    return value


def _unknown_fields(
    obj: dict[str, Any], allowed: set[str], path: str, errors: list[str]
) -> None:
    for key in sorted(set(obj) - allowed):
        errors.append(f"{path}.{key} is not declared in schema version 1")


def _string(obj: dict[str, Any], key: str, path: str, errors: list[str]) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} must be a non-empty string")
        return ""
    return value.strip()


def _https_url(value: str, path: str, errors: list[str]) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append(f"{path} must be an absolute https URL")


def _timestamp(value: str, path: str, errors: list[str]) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        errors.append(f"{path} must be an ISO 8601 timestamp with a timezone")


def _link(value: Any, path: str, errors: list[str]) -> None:
    link = _required_object(value, path, errors)
    _unknown_fields(link, LINK_FIELDS, path, errors)
    name = _string(link, "name", path, errors)
    url = _string(link, "url", path, errors)
    if name and len(name) > 80:
        errors.append(f"{path}.name must be 80 characters or fewer")
    if url:
        _https_url(url, f"{path}.url", errors)


def validate_news(document: Any) -> list[str]:
    """Return human-readable validation errors; an empty list means valid."""

    errors: list[str] = []
    root = _required_object(document, "$", errors)
    if not root:
        return errors or ["$ must not be empty"]
    _unknown_fields(root, ROOT_FIELDS, "$", errors)

    if root.get("schema_version") != 1:
        errors.append("$.schema_version must equal 1")

    edition = _required_object(root.get("edition"), "$.edition", errors)
    _unknown_fields(edition, EDITION_FIELDS, "$.edition", errors)
    edition_date = _string(edition, "date", "$.edition", errors)
    if edition_date:
        try:
            date.fromisoformat(edition_date)
        except ValueError:
            errors.append("$.edition.date must use YYYY-MM-DD")
    _string(edition, "title", "$.edition", errors)
    _string(edition, "kicker", "$.edition", errors)
    status = _string(edition, "status", "$.edition", errors)
    if status and status not in {"demo", "live"}:
        errors.append("$.edition.status must be 'demo' or 'live'")
    updated_at = _string(edition, "updated_at", "$.edition", errors)
    if updated_at:
        _timestamp(updated_at, "$.edition.updated_at", errors)

    sections = _required_list(root.get("sections"), "$.sections", errors)
    if sections and sections != list(SECTIONS):
        errors.append(f"$.sections must equal {list(SECTIONS)!r} in that order")

    stories = _required_list(root.get("stories"), "$.stories", errors)
    seen_ids: set[str] = set()
    for index, raw_story in enumerate(stories):
        path = f"$.stories[{index}]"
        story = _required_object(raw_story, path, errors)
        _unknown_fields(story, STORY_FIELDS, path, errors)
        story_id = _string(story, "id", path, errors)
        if story_id in seen_ids:
            errors.append(f"{path}.id is duplicate: {story_id!r}")
        if story_id:
            seen_ids.add(story_id)

        section = _string(story, "section", path, errors)
        if section and section not in SECTIONS:
            errors.append(f"{path}.section must be one of {list(SECTIONS)!r}")
        rank = story.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            errors.append(f"{path}.rank must be a positive integer")
        _string(story, "story_type", path, errors)
        title = _string(story, "title", path, errors)
        if title and len(title) > 180:
            errors.append(f"{path}.title must be 180 characters or fewer")
        _string(story, "summary", path, errors)
        _link(story.get("source"), f"{path}.source", errors)
        canonical_url = _string(story, "canonical_url", path, errors)
        if canonical_url:
            _https_url(canonical_url, f"{path}.canonical_url", errors)
        published_at = _string(story, "published_at", path, errors)
        if published_at:
            _timestamp(published_at, f"{path}.published_at", errors)

        corroboration = _required_list(
            story.get("corroboration"), f"{path}.corroboration", errors
        )
        for link_index, link in enumerate(corroboration):
            _link(link, f"{path}.corroboration[{link_index}]", errors)

        quality = _required_object(story.get("quality"), f"{path}.quality", errors)
        _unknown_fields(quality, QUALITY_FIELDS, f"{path}.quality", errors)
        signal = _string(quality, "signal", f"{path}.quality", errors)
        if signal and signal not in QUALITY_SIGNALS:
            errors.append(
                f"{path}.quality.signal must be one of {sorted(QUALITY_SIGNALS)!r}"
            )
        confidence = _string(quality, "confidence", f"{path}.quality", errors)
        if confidence and confidence not in CONFIDENCE_LEVELS:
            errors.append(
                f"{path}.quality.confidence must be one of {sorted(CONFIDENCE_LEVELS)!r}"
            )
        _string(quality, "note", f"{path}.quality", errors)

        tags = _required_list(story.get("tags"), f"{path}.tags", errors)
        if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            errors.append(f"{path}.tags must contain only non-empty strings")

    lead_story_id = _string(root, "lead_story_id", "$", errors)
    if lead_story_id and lead_story_id not in seen_ids:
        errors.append("$.lead_story_id must reference an existing story id")
    return errors


def validate_production_coverage(document: Any) -> list[str]:
    """Return publication-gate errors for a structurally valid live edition."""

    if not isinstance(document, dict):
        return []
    edition = document.get("edition")
    stories = document.get("stories")
    if (
        isinstance(edition, dict)
        and edition.get("status") == "live"
        and isinstance(stories, list)
        and len(stories) < 12
    ):
        return [f"live editions need at least 12 stories; found {len(stories)}"]
    return []


def load_news(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError as exc:
        raise ValidationError([f"{path} does not exist"]) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError([f"{path} is not valid JSON: {exc.msg}"]) from exc
    errors = validate_news(document)
    if errors:
        raise ValidationError(errors)
    return document


def _atomic_write_json(document: Any, target: Path) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _write_archive_index(target: Path, current_date: str) -> None:
    archive_dir = target.parent / "archive"
    editions = [
        {"date": current_date, "url": "./data/news.json", "current": True}
    ]
    if archive_dir.is_dir():
        for archive_path in archive_dir.glob("*.json"):
            try:
                archived = load_news(archive_path)
            except ValidationError:
                continue
            archive_date = archived["edition"]["date"]
            if archive_date == current_date:
                continue
            editions.append({
                "date": archive_date,
                "url": f"./data/archive/{archive_date}.json",
                "current": False,
            })
    editions[1:] = sorted(editions[1:], key=lambda item: item["date"], reverse=True)
    _atomic_write_json({"editions": editions}, target.parent / "archive.json")


def atomic_ingest(candidate: Path, target: Path) -> None:
    """Validate, archive the prior day, then atomically publish the new edition."""

    document = load_news(Path(candidate))
    target = Path(target)
    previous = load_news(target) if target.exists() else None
    current_date = document["edition"]["date"]
    if previous and previous["edition"]["date"] != current_date:
        archive_target = target.parent / "archive" / f"{previous['edition']['date']}.json"
        _atomic_write_json(previous, archive_target)
    _atomic_write_json(document, target)
    _write_archive_index(target, current_date)


def build_site(source: Path = DEFAULT_SOURCE, output: Path = DEFAULT_OUTPUT) -> None:
    """Validate the edition before replacing the generated static output."""

    source = Path(source).resolve()
    output = Path(output).resolve()
    load_news(source / NEWS_FILE)
    if not (source / "index.html").is_file():
        raise ValidationError([f"{source / 'index.html'} does not exist"])
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        shutil.rmtree(stage)
        shutil.copytree(source, stage)
        if output.exists():
            if output.is_dir():
                shutil.rmtree(output)
            else:
                output.unlink()
        os.replace(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    build = subparsers.add_parser("build", help="validate public/ and copy it to dist/")
    build.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    validate = subparsers.add_parser("validate", help="validate an edition JSON file")
    validate.add_argument(
        "--production",
        action="store_true",
        help="also enforce minimum live-edition coverage",
    )
    validate.add_argument("candidate", type=Path)
    ingest = subparsers.add_parser(
        "ingest", help="validate and atomically replace public/data/news.json"
    )
    ingest.add_argument("candidate", type=Path)
    ingest.add_argument("--target", type=Path, default=DEFAULT_SOURCE / NEWS_FILE)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    command = args.command or "build"
    try:
        if command == "validate":
            document = load_news(args.candidate)
            coverage_errors = validate_production_coverage(document) if args.production else []
            if coverage_errors:
                raise ValidationError(coverage_errors)
            print(f"Valid: {args.candidate}")
        elif command == "ingest":
            atomic_ingest(args.candidate, args.target)
            print(f"Ingested atomically: {args.target}")
        else:
            source = getattr(args, "source", DEFAULT_SOURCE)
            output = getattr(args, "output", DEFAULT_OUTPUT)
            build_site(source, output)
            print(f"Built static site: {output}")
    except ValidationError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
