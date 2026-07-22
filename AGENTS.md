# Repository Guidelines

## Project Structure & Module Organization

This is a Python package using a `src/` layout. Library code lives in `src/csa_google_workspace/`: `workspace.py` is the public entry point, `backend.py` contains the real and fake backends, `base.py` and `comments.py` hold shared document/comment models, and `documents/` contains Docs, Sheets, and Slides implementations. Unit tests live in `tests/`; live Google tests are isolated under `tests/integration/`. Design notes and phased plans are in `docs/superpowers/`, API research is in `research/`, and empirical probes live in `experiments/`.

## Build, Test, and Development Commands

Use Python 3.10 or newer.

```bash
pip install -e ".[dev]"
pytest -q
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/
```

`pip install -e ".[dev]"` installs the package plus pytest for local development. `pytest -q` runs the offline unit suite using `FakeBackend`; it should not require network access or Google credentials. The integration command is opt-in and uses real Google APIs.

## Coding Style & Naming Conventions

Follow standard Python style: 4-space indentation, clear type hints on public interfaces, and small modules aligned with the existing architecture. Use `snake_case` for functions, methods, variables, and test names; use `PascalCase` for classes such as `Workspace`, `Comment`, and document types. Keep public APIs importable from the package root when they are intended for users. No formatter or linter is configured in `pyproject.toml`, so keep edits consistent with nearby code.

## Testing Guidelines

Add or update `tests/test_*.py` for behavior changes. Prefer unit tests against `FakeBackend` for deterministic coverage, especially for comment mutation, content read/write, and error translation. Place real API coverage in `tests/integration/` and keep it gated by `CSA_GW_INTEGRATION=1`. Do not make ordinary unit tests depend on credentials, network state, or live Google documents.

## Commit & Pull Request Guidelines

Recent history uses conventional prefixes such as `feat:`, `fix:`, `docs:`, and `test:`; keep commit subjects short and imperative, for example `fix: preserve deleted comment metadata`. Work on a branch and open a PR for every change. PRs should describe the behavior change, list tests run, link related issues or plans, and note any Google API or credential implications.

## Security & Configuration Tips

Never commit OAuth secrets, tokens, probe transcripts, or extracted document data. `.gitignore` already excludes `credentials.json`, `token*.json`, and experiment transcript outputs. Treat `research/` and `experiments/*/RESULTS.md` as source material when Google API behavior is unclear.
