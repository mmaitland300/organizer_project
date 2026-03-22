# Workflow Walkthrough Artifact

This artifact documents one realistic end-to-end workflow so a reviewer can
quickly see how the application is intended to be used in practice.

## Scenario

- Local sample library contains mixed one-shots and loops
- Goal: ingest files, identify duplicates, enrich metadata, and find similar
  candidates for sound selection

## Preconditions

- App starts successfully with `python main.py`
- Database path is known (`MUSICORG_DB_PATH` or default `~/.musicians_organizer.db`)
- A test folder with audio files is available (for example `D:\samples\demo_pack`)

## Steps and Expected Outcomes

1. **Scan a folder**
   - Action: choose root folder in the UI and run scan.
   - Expected: progress increments; file table populates; existing records update
     rather than duplicating paths.

2. **Run duplicate detection**
   - Action: trigger duplicate detection from the main workflow.
   - Expected: grouped results are shown for files with matching size + MD5.
   - Constraint: hashing can be slow on very large files.

3. **Run advanced analysis**
   - Action: run analysis for scanned records.
   - Expected: additional feature columns are populated (for example
     loudness/pitch/attack and MFCC values where available).
   - Constraint: CPU cost increases with library size.

4. **Filter and tag**
   - Action: apply filters (key/BPM/tag/feature ranges) and edit tags.
   - Expected: table view narrows deterministically by filter criteria and
     updates persist after restart.

5. **Find similar samples**
   - Action: select a reference file and request similar samples.
   - Expected: ranked neighbors are returned based on stored feature distance.
   - Constraint: output quality depends on feature coverage and distribution.

## Optional DB Verification

These checks are optional but useful for proving persistence after workflow steps:

```bash
python - <<'PY'
import os
import sqlite3

db_path = os.environ.get("MUSICORG_DB_PATH", os.path.expanduser("~/.musicians_organizer.db"))
con = sqlite3.connect(db_path)
cur = con.cursor()

cur.execute("SELECT COUNT(*) FROM files;")
print("rows:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM files WHERE loudness_lufs IS NOT NULL;")
print("rows_with_lufs:", cur.fetchone()[0])

con.close()
PY
```

## Failure Modes Observed in Practice

- Unsupported or corrupted files are skipped with warnings during scan.
- Missing media/system libraries can disable parts of playback/analysis.
- Similarity results degrade when many records are missing feature values.
