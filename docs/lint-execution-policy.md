# Lint Execution Policy (Locked Mode)

This document defines the operating mode for the Flake8 cleanup campaign.

## Policy Verification

- Flake8 source of truth: `.flake8`
- Black/isort config source of truth: `pyproject.toml`
- CI flake8 scope: `config services models utils main.py`
- CI matrix: Python `3.10` and `3.11`
- Local lint campaign runtime: Python `3.11` via repo-local `.venv`

## Preflight (Required Before Any Lint Branch)

1. Validate local venv interpreter:
   - `.\.venv\Scripts\python.exe --version`
2. If validation fails, recreate `.venv`:
   - `py -3.11 -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
   - `python -m pip install --upgrade pip`
   - `python -m pip install -r requirements.txt`
   - `python -m pip install -r requirements-dev.txt`
3. Use the repo-local interpreter command form for all lint branches:
   - `.\.venv\Scripts\python.exe -m ...`

## Command Templates (Locked)

- Scoped flake8 (matches CI scope):
  - `.\.venv\Scripts\python.exe -m flake8 config services models utils main.py`
- Targeted flake8:
  - `.\.venv\Scripts\python.exe -m flake8 <path-or-paths>`
- Black check:
  - `.\.venv\Scripts\python.exe -m black --check <path-or-paths>`
- isort check:
  - `.\.venv\Scripts\python.exe -m isort --check-only <path-or-paths>`
- Mypy full:
  - `.\.venv\Scripts\python.exe -m mypy .`
- Pytest full:
  - `.\.venv\Scripts\python.exe -m pytest -q --maxfail=1 --disable-warnings`

## Safeguards

- Lint-only changes; no behavior changes.
- Preserve `main.py` import bootstrap semantics (`sys.path` setup and current `E402` treatment).
- Handle `config/settings.py` regex edits manually, not mechanically.
- Keep branch diffs reviewable; split large files into multiple passes as needed.

## Execution Order

1. `lint/policy-verify`
2. `lint/baseline-snapshot`
3. `lint/non-e501-final-pass`
4. `lint/services-e501-pass-1`
5. `lint/services-database-manager-e501-pass-1`
6. `lint/services-database-manager-e501-pass-2`
7. `lint/models-e501-pass-1`
8. `lint/config-main-utils-e501-pass`
9. `ci/flake8-blocking-reenable`
