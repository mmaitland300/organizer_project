# Flake8 Baseline Snapshot

This baseline captures the state of the scoped CI flake8 target before the
cleanup passes.

## Runtime and Policy

- Local interpreter: `.\.venv\Scripts\python.exe` (Python 3.11.4)
- Scoped command:
  - `.\.venv\Scripts\python.exe -m flake8 config services models utils main.py`
- Flake8 policy source: `.flake8`
  - `max-line-length = 88`
  - `extend-ignore = E203, W503`
- CI matrix note: CI still runs Python 3.10 and 3.11; this baseline is local 3.11.

## Baseline Totals

- Total findings: `149`

### Findings by Code

- `E501`: 149

### Top Files by Count

1. `services/database_manager.py`: 53
2. `models/file_model.py`: 51
3. `services/analysis_engine.py`: 12
4. `services/file_scanner.py`: 8
5. `services/spectrogram_service.py`: 7
6. `services/auto_tagger.py`: 4
7. `services/spectrogram_plotter.py`: 3
8. `config/settings.py`: 3
9. `services/advanced_analysis_worker.py`: 3
10. `services/hash_worker.py`: 2

## Notes for Next Branches

- Non-`E501` findings are currently zero in the scoped command.
- Highest-churn files are `services/database_manager.py` and `models/file_model.py`,
  which is why they are split into dedicated passes.
