# Musicians Organizer

Musicians Organizer is a desktop tool for working with large local audio libraries.
It focuses on practical file-library operations: scan folders, persist metadata,
run analysis, filter/tag results, and handle duplicates without leaving the app.

This project exists because once a sample library grows, folder names alone stop
being enough. You need a repeatable workflow for finding files, tracking metadata,
and cleaning the library over time.

## Who this is for

- Music producers and sound designers with large local sample libraries
- People who want local, inspectable workflows over cloud cataloging tools
- Users comfortable with Python + desktop tooling tradeoffs

## Current Status

### Working now

- Recursive folder scanning with metadata extraction
- SQLite-backed persistence (SQLAlchemy Core) with Alembic migrations
- Filtering by filename, musical key, BPM, tags, used status, and several
  extracted audio features
- Duplicate detection using size + MD5 hash checks
- Advanced feature extraction in background workers (including MFCC set and
  additional descriptors)
- Similarity recommendations based on stored features
- Waveform/spectrogram dialogs and in-app preview controls
- Multi-dimensional tagging support (for example `instrument:KICK`)

### Partial or rough edges

- Heavy dependency stack (PyQt5 + audio/scientific packages) can make setup
  and packaging fragile on some systems
- Auto-tagging is heuristic, not deterministic ground truth
- Similarity quality depends on feature completeness and distribution in your
  own library
- "Send to Cubase" integration is narrow by design and not a general DAW bridge

## Quick Start (Deterministic Path)

Target runtime is Python 3.11. CI currently exercises Python 3.10 and 3.11.

1) Clone and enter the repository:

```bash
git clone https://github.com/mmaitland300/organizer_project.git
cd organizer_project
```

2) Create and activate a virtual environment:

Windows (PowerShell):

```bash
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If `py` is unavailable, use an explicit Python 3.11 executable path.

macOS / Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

3) Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

4) Run the app:

```bash
python main.py
```

## Database and Environment Notes

- Default DB path: `~/.musicians_organizer.db`
- Override DB path with: `MUSICORG_DB_PATH`
- Alembic migration scripts live in `migrations/`

If you need to run migrations manually:

```bash
alembic upgrade head
```

## Reproducible Verification Steps

Run from the repository root with your virtual environment active.
These are the same check commands used in CI:

```bash
python -m black --check .
python -m isort --check-only .
python -m flake8 .
python -m mypy .
python -m pytest -q --maxfail=1 --disable-warnings
```

## Architecture and Runtime Workflow

Core flow is:

1. Scan files from selected root folder
2. Persist/update records in SQLite
3. Run analysis workers for feature extraction
4. Filter/search/tag records in the UI
5. Inspect/manage duplicates and related files

Main runtime path:

- `main.py` initializes Qt app and database manager
- `ui/main_window.py` owns UI state, model, and action wiring
- `ui/controllers.py` coordinates background workers and state transitions
- `services/file_scanner.py` handles scan + incremental sync behavior
- `services/database_manager.py` manages upsert/query/statistics/similarity logic
- `services/schema.py` + `migrations/` define schema and migrations

## Tradeoffs and Limitations

- **Operational cost:** Advanced analysis is CPU-heavy on large libraries.
- **Dependency constraints:** Audio + plotting stacks can be sensitive to OS
  and local media backend differences.
- **Heuristic metadata:** Key/BPM/tag inference can be wrong; manual review is
  still part of the workflow.
- **Similarity model scope:** Distance calculations are feature-based and tuned
  for practical retrieval, not musicological correctness.
- **Desktop scope:** This is a local desktop workflow tool, not a collaborative
  service or cloud pipeline.

## Failure Modes to Expect

- Missing optional system media libraries can reduce playback/analysis features.
- Corrupted/unreadable files may be skipped with warnings during scan.
- Large scans can take time; cancellation and progress handling are implemented
  but long-running operations still need user patience.
- Inconsistent feature coverage across files can reduce similarity quality.

## Unfinished Scope

- Better packaging/distribution workflow for non-dev users
- More robust progress/error visibility for long analysis jobs
- Additional workflow-oriented tagging improvements
- Better cross-DAW export/integration primitives (currently Cubase-specific path)

## Project Structure

```text
organizer_project/
|-- main.py
|-- config/
|-- models/
|-- services/
|-- ui/
|-- migrations/
|-- tests/
|-- requirements.txt
|-- requirements-dev.txt
`-- .github/workflows/ci.yml
```
