# Releasing to PyPI

Publishing is automated: **publishing a GitHub Release** triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which runs the tests,
builds the sdist + wheel, and uploads to PyPI via **Trusted Publishing (OIDC)** — no API
token is stored anywhere.

## One-time setup (maintainer, on PyPI)

Do this once, before the first release. PyPI supports a "pending publisher", so the project
need not exist yet.

1. Sign in to <https://pypi.org> with the account that will own the project (the CSA org
   account, or a maintainer's).
2. Go to **Your projects → Publishing** (or, for a brand-new project,
   <https://pypi.org/manage/account/publishing/>) and **Add a pending publisher** with:
   - **PyPI project name:** `csa-google-workspace`
   - **Owner:** `CloudSecurityAlliance`
   - **Repository name:** `csa-google-workspace`
   - **Workflow name:** `release.yml`
   - **Environment name:** *(leave blank)*
3. That's it — no token, no GitHub secret. GitHub Actions authenticates to PyPI over OIDC.

*(Optional hardening for later: add a GitHub Environment named e.g. `pypi` with required
reviewers, set `environment: pypi` on the `publish` job, and put the same name in the PyPI
publisher config — this gates each publish behind a manual approval.)*

## Cut a release

1. Make sure `main` is green and pick the version. Bump it in **one place** —
   `src/csa_google_workspace/__init__.py` `__version__` (pyproject reads it dynamically) —
   and add a dated entry to `CHANGELOG.md`. Merge that via the normal PR flow.
2. Tag and publish a GitHub Release on the merge commit:
   ```bash
   gh release create v0.1.0 --title v0.1.0 --notes-file <(sed -n '/## 2026-.*v0.1.0/,/^## /p' CHANGELOG.md)
   # or: gh release create v0.1.0 --generate-notes
   ```
   The tag **must** match the version (`v0.1.0` ↔ `__version__ = "0.1.0"`).
3. Publishing the release starts the `release` workflow. Watch it:
   ```bash
   gh run watch
   ```
4. Verify the upload — <https://pypi.org/project/csa-google-workspace/> — then in a clean venv:
   ```bash
   pip install csa-google-workspace
   python -c "import csa_google_workspace; print(csa_google_workspace.__version__)"
   ```

## Notes

- A PyPI version number is **permanent** — it can be yanked but never re-uploaded. Get the
  version right before publishing.
- `requires-python` is `>=3.10`; the wheel is pure-Python (`py3-none-any`).
- The package ships `py.typed`, so downstream `mypy`/`pyright` consume its type hints.
