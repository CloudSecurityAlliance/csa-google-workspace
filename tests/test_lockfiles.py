"""What CI installs is recorded here, and the two things that are deliberately not.

**T18.** Nothing in this tree pinned what the automation installed. Every job resolved
lower-bound-only ranges live from PyPI, including the release job whose entire output is the
artifact published under our name. `requirements/*.txt` fixes that with hash-pinned closures;
these tests assert the wiring, because a lockfile that exists and is not used is worse than
none - it reads as a control from the outside.

**The published ranges stay permissive**, and that is not an inconsistency. Pinning a
*library's* dependencies pushes a resolution problem onto every application that installs it.
The 2026-07-22 audit called the permissive ranges "benign and standard for a library"
(GA-#28); the 2026-08-27 one called unpinned CI a supply-chain gap (T18). Both are right about
different questions, and the split between `pyproject.toml` and `requirements/` is the answer
to both.

**Two carve-outs are asserted as carve-outs**, so that "fixing the inconsistency" fails here
with the reason attached rather than quietly removing a signal:

  * the `security` job resolves freely, because `pip-audit` reporting on our own lockfile
    would be reporting on the one environment nobody installs;
  * `pip` is the runner's, because `pip install --upgrade pip` is an unpinned fetch by the
    tool that is about to verify every other hash.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REQS = ROOT / "requirements"
TESTS_YML = ROOT / ".github/workflows/tests.yml"
DOC_CLAIMS_YML = ROOT / ".github/workflows/doc-claims.yml"
RELEASE_YML = ROOT / ".github/workflows/release.yml"

LOCKS = ["dev.txt", "build.txt", "build-backend.txt"]
# A pinned line: `name==version [; marker] \`
PIN = re.compile(r"^([A-Za-z0-9._-]+)==([^\s;\\]+)")


def lock(name: str) -> str:
    path = REQS / name
    if not path.exists():
        pytest.skip(f"{name} is not in this tree")
    return path.read_text(encoding="utf-8")


def pins(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if (m := PIN.match(line)):
            out[m.group(1).lower().replace("_", "-")] = m.group(2)
    return out


class TestEveryLockedRequirementCarriesHashes:
    """`--require-hashes` refuses an unhashed entry, so a lock missing them fails the install
    rather than installing something unverified. Asserted anyway: the failure would arrive in
    CI on an unrelated PR, and the diagnosis ("your lockfile was regenerated without
    --generate-hashes") is not one the error message offers."""

    @pytest.mark.parametrize("name", LOCKS)
    def test_no_pin_is_unhashed(self, name):
        text = lock(name)
        lines = text.splitlines()
        unhashed = []
        for i, line in enumerate(lines):
            if PIN.match(line) and "--hash=" not in "".join(lines[i:i + 3]):
                unhashed.append(line.split()[0])
        assert unhashed == [], f"{name}: {unhashed} are pinned without hashes"

    @pytest.mark.parametrize("name", LOCKS)
    def test_the_lock_is_not_empty(self, name):
        assert len(pins(lock(name))) >= 1, f"{name} pins nothing; a vacuous lock is not a lock"


class TestTheLockCoversWhatPyprojectDeclares:
    """The drift that a lockfile invites: a dependency added to `pyproject.toml` and not
    locked here installs in nobody's CI, and surfaces as an `ImportError` somewhere in the
    five-Python matrix - a true failure with a misleading cause. This fails on the PR that
    introduces it, in the `lint` job, naming the package."""

    def declared(self) -> set[str]:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        names: set[str] = set()
        for block in ("dependencies = [", "dev = ["):
            start = text.index(block)
            chunk = text[start:text.index("]", start)]
            for m in re.finditer(r"[\"']([A-Za-z0-9._-]+)\s*[><=~!]", chunk):
                names.add(m.group(1).lower().replace("_", "-"))
        return names

    def test_every_declared_dependency_is_locked(self):
        locked = pins(lock("dev.txt"))
        missing = sorted(n for n in self.declared() if n not in locked)
        assert missing == [], (
            f"{missing} are declared in pyproject.toml and absent from requirements/dev.txt. "
            f"Run scripts/lock.sh.")

    def test_the_parse_found_the_real_dependencies(self):
        """A regex that stopped matching would make the test above pass on air."""
        found = self.declared()
        assert {"pytest", "ruff", "mypy", "google-auth", "oauthlib"} <= found, found


class TestCiInstallsFromTheLock:
    @pytest.mark.parametrize("job", ["lint", "test"])
    def test_the_workflow_requires_hashes(self, job):
        text = TESTS_YML.read_text(encoding="utf-8")
        assert text.count("--require-hashes -r requirements/dev.txt") >= 2, (
            "the lint and test jobs must both install from the lock; a lockfile only some "
            "jobs use is a lockfile that does not bound CI")

    def test_the_project_goes_in_without_its_dependencies(self):
        """`--require-hashes` is all-or-nothing, so `-e .` has to be separate. Without
        `--no-deps` pip re-resolves the ranges and quietly un-pins what was just pinned."""
        text = TESTS_YML.read_text(encoding="utf-8")
        assert "pip install -e . --no-deps --no-build-isolation" in text

    @pytest.mark.parametrize("path", [TESTS_YML, RELEASE_YML, DOC_CLAIMS_YML])
    def test_the_editable_build_does_not_fetch_its_backend(self, path):
        """`pip install -e .` builds through PEP 517, which fetches `build-system.requires`
        from PyPI into an isolated env. Pinning the closure leaves that fetch untouched, so
        the backend goes in from the pinned file and `--no-build-isolation` makes the build
        use it instead of downloading its own."""
        text = path.read_text(encoding="utf-8")
        assert "--require-hashes -r requirements/build-backend.txt" in text
        # Scoped to the PINNED installs - the ones carrying `--no-deps`. The security job's
        # `pip install -e . pip-audit bandit` deliberately builds with isolation and resolves
        # freely, which is the same carve-out as the rest of that job: it is meant to look
        # like a real user's install. The first draft of this test flagged it, which is how
        # the exemption came to be written down rather than assumed.
        pinned = [ln for ln in text.splitlines()
                  if "pip install -e . --no-deps" in ln and not ln.strip().startswith("#")]
        assert pinned, f"{path.name} has no pinned editable install"
        for line in pinned:
            assert "--no-build-isolation" in line, (
                f"{path.name}: `{line.strip()}` builds with isolation, which fetches "
                f"setuptools from PyPI unpinned")

    def test_the_release_build_uses_the_lock_too(self):
        text = RELEASE_YML.read_text(encoding="utf-8")
        assert "--require-hashes -r requirements/dev.txt" in text, (
            "the suite that gates a tag must run against the recorded closure")
        assert "--require-hashes -r requirements/build.txt" in text


class TestTheBuildBackendIsPinnedThroughIsolation:
    """The piece a lockfile alone does not reach.

    `python -m build` creates its OWN isolated venv and installs `build-system.requires` into
    it from PyPI. Pinning `build` and `twine` in the outer environment leaves the code that
    actually writes the wheel resolving freely - in the job whose only output is the artifact.

    `PIP_CONSTRAINT` reaches inside, and was verified by falsification rather than assumed:
    with a constraint contradicting `build-system.requires = ["setuptools>=83"]` the build
    fails with a resolver conflict, so it is applied rather than silently ignored.
    """

    def test_the_constraint_is_set_on_the_build_step(self):
        text = RELEASE_YML.read_text(encoding="utf-8")
        assert "PIP_CONSTRAINT: requirements/build-backend.txt" in text

    def test_the_constraint_file_pins_the_declared_backend(self):
        backend = pins(lock("build-backend.txt"))
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        requires = re.search(r"requires\s*=\s*\[(.*?)\]", pyproject, re.S).group(1)
        for m in re.finditer(r"[\"']([A-Za-z0-9._-]+)\s*[><=~!]", requires):
            name = m.group(1).lower().replace("_", "-")
            assert name in backend, (
                f"{name} is in build-system.requires and not constrained; the isolated build "
                f"env would fetch it unpinned")

    def test_the_pinned_backend_satisfies_the_declared_floor(self):
        """A constraint BELOW build-system.requires does not fail closed in a useful way -
        it fails the release, at publish time, with a resolver conflict."""
        backend = pins(lock("build-backend.txt"))
        assert int(backend["setuptools"].split(".")[0]) >= 83, (
            f"setuptools pinned at {backend['setuptools']} but build-system.requires says "
            f">=83; the release would fail on a conflict")


class TestTheCarveOutsStayDeliberate:
    """Both of these look like oversights and are not. Asserted so that tidying them up trips
    a test carrying the reason, rather than silently removing a signal."""

    def test_the_security_job_still_resolves_freely(self):
        text = TESTS_YML.read_text(encoding="utf-8")
        security = text[text.index("  security:"):]
        assert "--require-hashes" not in security, (
            "the security job must NOT install from the lock: pip-audit exists to observe "
            "what a real install resolves to, and auditing our own lockfile audits the one "
            "environment nobody installs. See requirements/README.md.")
        assert "unpinned on purpose" in security, (
            "if the carve-out stops being labelled, the next reader fixes it")

    def test_pip_is_not_upgraded_before_it_verifies_hashes(self):
        for path in (TESTS_YML, RELEASE_YML):
            text = path.read_text(encoding="utf-8")
            offending = [ln for ln in text.splitlines()
                         if "--upgrade pip" in ln and not ln.strip().startswith("#")]
            assert offending == [], (
                f"{path.name} upgrades pip: an unpinned fetch from PyPI by the tool about to "
                f"verify every other hash. The runner's pip is used as shipped.")


class TestTheLockfilesAreReproducible:
    def test_the_script_pins_the_floor_not_the_local_interpreter(self):
        """`uv pip compile --universal` resolves against the interpreter it runs on, NOT the
        floor in `requires-python`, even with pyproject.toml as input. Measured: on 3.12 it
        pinned `rpds-py==2026.6.3` (requires >=3.11), which installs on four matrix legs and
        fails the fifth. The explicit floor is what makes the lock serve all five."""
        script = (ROOT / "scripts/lock.sh").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        floor = re.search(r'requires-python\s*=\s*">=([0-9.]+)"', pyproject).group(1)
        assert f"FLOOR={floor}" in script, (
            f"scripts/lock.sh must compile at the requires-python floor ({floor})")

    def test_the_oldest_python_has_its_own_marked_entries(self):
        """The observable consequence of the above: a correct lock carries version-conditional
        entries, because one version set does not serve 3.10 through 3.14."""
        text = lock("dev.txt")
        assert "python_full_version < '3.11'" in text, (
            "no 3.10-specific pins - the lock was probably compiled on a newer interpreter, "
            "and will fail the 3.10 matrix leg at install time")


class TestTheConstraintTrapStaysDocumented:
    """`PIP_CONSTRAINT` is the obvious way to pin an editable install's build backend, and it
    does not work: a constraints file **carrying hashes** puts pip into hash-checking mode for
    the whole invocation, and an editable requirement then fails outright -

        ERROR: The editable requirement file:///... cannot be installed when requiring
        hashes, because there is no single file to hash.

    Measured, not read. It is why the two workflows pin the backend by installing it and
    passing `--no-build-isolation` instead, and why `PIP_CONSTRAINT` appears on exactly one
    step - the `python -m build` step, which installs nothing editable.

    Without this test the next person hits the same wall, in CI, on an unrelated PR.
    """

    def test_pip_constraint_is_only_on_the_build_step(self):
        text = RELEASE_YML.read_text(encoding="utf-8")
        uses = [ln for ln in text.splitlines()
                if "PIP_CONSTRAINT" in ln and not ln.strip().startswith("#")]
        assert len(uses) == 1, (
            f"PIP_CONSTRAINT appears {len(uses)} times; a hashed constraints file forces "
            f"hash-checking mode, so any step doing an editable install will fail")

    def test_no_workflow_sets_it_at_job_or_workflow_level(self):
        """Job-level `env:` would reach the editable installs and break them. The indent is
        the tell: a step-level `env:` block sits deeper than a job-level one."""
        for path in (TESTS_YML, RELEASE_YML):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "PIP_CONSTRAINT" in line and not line.strip().startswith("#"):
                    assert len(line) - len(line.lstrip()) >= 10, (
                        f"{path.name}: PIP_CONSTRAINT looks job- or workflow-level; it must "
                        f"be scoped to the `python -m build` step")

    def test_the_reason_is_written_down_where_it_will_be_read(self):
        combined = (TESTS_YML.read_text(encoding="utf-8")
                    + (REQS / "README.md").read_text(encoding="utf-8"))
        assert "hash-checking mode" in combined or "no single file to hash" in combined, (
            "the trap has to be recorded next to the code it explains, or the next reader "
            "reaches for PIP_CONSTRAINT and finds out in CI")


class TestDependabotDoesNotTouchTheLockfiles:
    """It cannot maintain them, and it proved it.

    `/requirements` was in `dependabot.yml` from v0.30.8 until 2026-08-28. The first run opened
    PR #225 bumping `pydantic-core` 2.46.4 -> 2.48.0 in `requirements/dev.txt` while leaving
    `pydantic==2.13.4`, which pins `pydantic-core==2.46.4`. Every job failed with
    `ResolutionImpossible`.

    That is not a bug in the PR. **Dependabot edits individual pinned lines**, and a fully-pinned
    transitive lock has to be *re-resolved as a graph*. Pointing it back at this directory would
    reintroduce a weekly red PR, so this test states the reason rather than leaving the omission
    to look like an oversight somebody should tidy up.
    """

    DEPENDABOT = ROOT / ".github/dependabot.yml"
    RELOCK = ROOT / ".github/workflows/relock.yml"

    def test_dependabot_does_not_target_requirements(self):
        text = self.DEPENDABOT.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "director" in stripped and "requirements" in stripped:
                pytest.fail(
                    f"dependabot.yml targets requirements/ ({stripped!r}). It cannot maintain a "
                    f"fully-pinned lock - it patches single lines and cannot re-resolve. See "
                    f"PR #225. relock.yml does this job.")

    def test_dependabot_still_watches_pyproject(self):
        """Removing the lockfiles must not remove advisory coverage of the declared ranges,
        which is the thing Dependabot is genuinely good at."""
        text = self.DEPENDABOT.read_text(encoding="utf-8")
        assert "package-ecosystem: pip" in text

    def test_the_replacement_exists_and_is_scheduled(self):
        text = self.RELOCK.read_text(encoding="utf-8")
        assert "schedule:" in text and "cron:" in text
        assert "lock.sh --upgrade" in text, "the whole point is re-resolving, not patching"

    def test_the_replacement_holds_no_write_permission_on_contents(self):
        """It reports; it does not push. A PR opened with the repository's GITHUB_TOKEN does not
        trigger other workflows, so it would arrive with zero checks and could never merge past
        branch protection - while looking reviewed. Opening one properly needs a write-scoped PAT
        in a public repo, which was declined."""
        text = self.RELOCK.read_text(encoding="utf-8")
        assert "contents: read" in text
        assert "contents: write" not in text

    def test_uv_itself_is_hash_pinned(self):
        """The tool that regenerates the locks must not be an unpinned download - that would put
        the whole chain back where it started."""
        assert (REQS / "uv.txt").exists()
        assert "uv" in pins(lock("uv.txt"))
        assert "--require-hashes -r requirements/uv.txt" in self.RELOCK.read_text(
            encoding="utf-8")


class TestTheUniversalLockKeepsItsEnvironmentMarkers:
    r"""A `--universal` lock is ONE file for every platform, and the markers are what make that
    work. Strip them and the file still parses, still has hashes, and still passes every other
    test in this module - while installing Linux-only packages on Windows and, worse, DROPPING
    the entries that only apply somewhere else.

    Not hypothetical. Dependabot PR #456 (2026-09-15) proposed exactly this against
    `requirements/build.txt` while bumping one version:

        - colorama==0.4.6 ; os_name == 'nt'                       <- removed entirely
        - cffi==2.1.1 ; ... and sys_platform == 'linux'     ->   + cffi==2.1.1
        - backports-tarfile==1.2.0 ; python_full_version < '3.12' -> + backports-tarfile==1.2.0

    It resolved the lock for ITS OWN environment and flattened the result. `requirements/README.md`
    already says why that cannot work - "Dependabot edits individual pinned lines; a fully-pinned
    transitive lock has to be RE-RESOLVED as a graph" - and `.github/dependabot.yml` says
    `/requirements` is deliberately unlisted. Neither stopped it: the PR was opened anyway, and
    **nothing in this suite could see the damage**, because every existing assertion here is about
    a pin being present and hashed rather than about it being CONDITIONAL.

    So this is the guard for the defect rather than for the tool. A hand-edit does it too.
    """

    # Counted from the real files 2026-09-16, floored well below so ordinary resolution churn
    # does not trip it. Zero is the failure that matters; the floor only makes it louder sooner.
    MARKERED = {"dev.txt": 8, "build.txt": 8}

    @pytest.mark.parametrize("name", sorted(MARKERED))
    def test_the_lock_still_carries_conditional_pins(self, name):
        text = (REQS / name).read_text(encoding="utf-8")
        markered = [ln for ln in text.splitlines() if re.match(r"^[A-Za-z0-9._-]+==\S+ ; ", ln)]
        assert len(markered) >= self.MARKERED[name], (
            f"{name} carries {len(markered)} conditional pins, expected at least "
            f"{self.MARKERED[name]}. A --universal lock that lost its environment markers has "
            f"been re-resolved for ONE environment - it will install Linux-only packages "
            f"everywhere and silently drop the ones that only apply elsewhere. Regenerate with "
            f"./scripts/lock.sh rather than editing pins by hand.")

    def test_the_windows_only_pin_is_still_conditional(self):
        """`colorama ; os_name == 'nt'` is the single most legible instance: unconditional it is
        installed on Linux where nothing wants it, and DELETED - which is what #456 did - it is
        missing on the platform that needs it. Named explicitly because a count can be satisfied
        while the one that matters is gone."""
        text = (REQS / "build.txt").read_text(encoding="utf-8")
        assert re.search(r"^colorama==\S+ ; os_name == 'nt'", text, re.M), (
            "colorama lost its `os_name == 'nt'` marker, or was dropped from build.txt")

    def test_the_counted_floors_name_files_that_exist(self):
        """A floor for a file that has been renamed would pass vacuously forever."""
        assert set(self.MARKERED) <= set(LOCKS), f"{set(self.MARKERED) - set(LOCKS)} not in LOCKS"
