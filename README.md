# The Daily Signal

A static, dependency-free personal newspaper for four consequential frontiers: Bitcoin, AI, Robotics, and Longevity. The browser renders the complete edition from `public/data/news.json`; no story copy is compiled into the HTML or JavaScript.

The visual structure is editorial rather than dashboard-like: **Explore** gives one lead story room to breathe, while **Monitor** presents the remaining reading queue in rank order. Dark mode is the default; a remembered light-mode choice, keyboard focus, small-screen layouts, and reduced-motion preferences are built in.

> **DEMO contract:** `docs/news.example.json` remains clearly marked demonstration content for producer development and is not live reporting. The published `public/data/news.json` is the live edition. There are no engagement, popularity, performance, market, or invented audience metrics.

## Quick start

Python 3.9+ is the only required development tool. A current Node executable is optional and lets the unittest suite execute the small pure-JavaScript behavior checks; those checks are skipped when Node is unavailable.

```sh
python -m unittest discover -v
python scripts/build.py build
python -m http.server 8000 --directory public
```

Open `http://localhost:8000`. Serve the directory instead of opening `index.html` directly because browsers do not reliably allow `fetch()` from `file://` pages.

The build validates the current feed first, then recreates `dist/` as a deployable copy of `public/`:

```sh
python scripts/build.py build
```

## Daily data contract

The normative JSON Schema is [`docs/news.schema.json`](docs/news.schema.json). A compact complete payload is in [`docs/news.example.json`](docs/news.example.json). The stdlib runtime validator mirrors the schema and adds relational checks JSON Schema cannot express conveniently: story IDs must be unique and `lead_story_id` must name an existing story.

Top-level shape:

| Field | Meaning |
| --- | --- |
| `schema_version` | Must be `1`; change this for a breaking contract revision. |
| `edition` | Edition date, display copy, `demo`/`live` status, and timezone-aware update time. |
| `sections` | Exactly `Bitcoin`, `AI`, `Robotics`, `Longevity`, in display order. |
| `lead_story_id` | ID of the story used for the all-topic Explore lead. |
| `stories` | Ranked story records. Lower positive `rank` values appear first. |

Each story supplies its section, type, timestamp, summary, primary source, canonical link, and zero or more distinct corroborating links. The displayed corroboration count is derived—not supplied—from the primary source plus the `corroboration` array.

`quality.signal` is one of:

- `primary`: the canonical item is itself the source material;
- `corroborated`: independent links support the central claim;
- `developing`: the facts or interpretation may still change;
- `analysis`: synthesis or interpretation rather than a new primary fact.

`quality.confidence` is a transparent editorial label (`high`, `medium`, or `low`), never a fabricated numeric score. `quality.note` should briefly justify the assignment; it appears as a native tooltip.

All source and canonical URLs must be absolute HTTPS links. Timestamps must be ISO 8601 with a timezone. Unknown fields are rejected so upstream feed drift fails loudly instead of silently changing the UI.

## Ingest interface

An external research job should write its candidate to a separate path, then call the checked atomic ingest command:

```sh
python scripts/build.py validate /absolute/path/to/candidate.json
python scripts/build.py ingest /absolute/path/to/candidate.json
python scripts/build.py build
```

`ingest` performs validation again. When the candidate date changes, it first preserves the outgoing edition at `public/data/archive/YYYY-MM-DD.json`; it then serializes normalized UTF-8 JSON to temporary files, flushes them, and calls `os.replace` to atomically publish `public/data/news.json` and `public/data/archive.json`. The browser's **Edition archive** selector reads that index, so tomorrow's ingest automatically keeps today's paper available. A rejected candidate leaves the previous edition untouched. Do not stream or copy bytes directly over the live file.

For a non-default target (useful in pipeline tests):

```sh
python scripts/build.py ingest candidate.json --target /path/to/public/data/news.json
```

The producer owns research, deduplication, ranking, and editorial assessment. It must emit the complete edition; ingest is whole-file replacement, not a merge. Set `edition.status` to `live` only after replacing all demonstration content.

## Test and verification

Run everything:

```sh
python -m unittest discover -v
```

The suite covers schema/runtime validation, safe atomic ingest, build failure behavior, semantic landmarks, keyboard and theme hooks, responsive and reduced-motion CSS, safe URL/text handling, deterministic ranking/filtering, lead selection, and empty/error messaging.

Useful focused checks:

```sh
python -m unittest tests.test_build -v
python -m unittest tests.test_web -v
python scripts/build.py validate public/data/news.json
```

## Static deployment

No server functions, redirects, environment variables, external fonts, or package installation are required. Asset URLs are relative, so the build also works under a GitHub project subpath. In every host, deploy the generated `dist/` directory and do not cache `data/news.json` immutably; the client also requests it with `cache: "no-store"`.

### Cloudflare Pages

- Connect the repository as a Pages project.
- Build command: `python scripts/build.py build`
- Build output directory: `dist`
- Root directory: repository root

### Vercel

- Import the repository as a project using the “Other” framework preset.
- Build command: `python scripts/build.py build`
- Output directory: `dist`
- Install command: leave empty.

### GitHub Pages

Use a GitHub Actions Pages workflow that checks out the repository, runs `python -m unittest discover -v`, runs `python scripts/build.py build`, uploads `dist/` with `actions/upload-pages-artifact`, and deploys it with `actions/deploy-pages`. Grant the workflow `pages: write` and `id-token: write`. This keeps generated output out of the source branch.

If the site is published at `https://owner.github.io/repository/`, no base-path edit is needed because all browser assets and the JSON fetch use `./` relative URLs.

## Project layout

```text
public/                 deployable source site
  index.html            semantic shell and rendering mounts
  styles.css            newspaper design, themes, responsive behavior
  news-core.js          pure ranking/safety helpers
  app.js                JSON loading and DOM rendering
  data/news.json        atomically replaceable current edition
  data/archive.json     current + historical edition index
  data/archive/         immutable date-addressed past editions
scripts/build.py        stdlib validator, ingest command, static builder
docs/news.schema.json   versioned JSON Schema
docs/news.example.json  complete producer example
tests/                  unittest suite
dist/                   generated deploy artifact (after build)
```

The project intentionally has no external JavaScript dependencies and no analytics or tracking code.
