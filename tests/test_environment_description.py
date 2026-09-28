"""What this machine gets called in a bug report, and what a missing package is called.

`_os_description` exists because `platform.release()` alone is close to useless in a report:
on macOS it gives the Darwin kernel version (25.6.0), which nobody recognises as the OS they
are running, and on Windows it gives `"10"` for Windows 11. Both platforms expose something
better, so both branches ask for it - and neither branch had ever been executed, because CI
is Linux and development is macOS.

These are NOT platform-locked, which is why they are tested rather than pragma'd: the
functions branch on `platform.system()` and read values from the `platform` module, all of
which a test can supply. What cannot be faked here is whether the real `platform` returns
what these assume, and that is a different question from whether the code handles it.
"""
from __future__ import annotations

import platform

import pytest

from csa_google_workspace import _environment


@pytest.fixture
def pretend(monkeypatch):
    """Make `platform` answer as a named OS would."""
    def as_os(system, **values):
        monkeypatch.setattr(platform, "system", lambda: system)
        for name, value in values.items():
            monkeypatch.setattr(platform, name, lambda v=value: v)
    return as_os


class TestOsDescription:
    def test_macos_reports_the_product_version_not_the_darwin_kernel(self, pretend):
        """`platform.release()` here is `"25.6.0"`. A reader seeing that in a bug report has
        to look up which macOS it means, and most will not."""
        pretend("Darwin", mac_ver=("26.0", ("", "", ""), "arm64"), release="25.6.0")
        assert _environment._os_description() == "macOS 26.0"

    def test_macos_with_no_product_version_names_darwin_explicitly(self, pretend):
        """Rather than "macOS " with nothing after it. The kernel version is still worth
        printing - it is labelled so nobody reads it as the OS version."""
        pretend("Darwin", mac_ver=("", ("", "", ""), ""), release="25.6.0")
        assert _environment._os_description() == "macOS (Darwin 25.6.0)"

    def test_windows_keeps_the_build_number_because_it_is_what_distinguishes_11(self, pretend):
        """`win32_ver()[0]` is `"10"` on Windows 11. The build in `platform.version()` is the
        only thing in either call that tells them apart - 22000 and above is 11 - so a
        description built from the release alone would call every Windows machine Windows 10."""
        pretend("Windows", win32_ver=("10", "10.0.22631", "SP0", "Multiprocessor Free"),
                version="10.0.22631")
        described = _environment._os_description()

        assert described.startswith("Windows 10")
        assert "22631" in described, "the build number is the part that identifies Windows 11"
        assert "SP0" in described

    def test_windows_fields_that_are_empty_are_left_out(self, pretend):
        """Modern Windows has no service pack, so that field is empty. Joining it in anyway
        produces a trailing space, and in a filename-shaped context a stray one is a bug."""
        pretend("Windows", win32_ver=("11", "10.0.26100", "", ""), version="10.0.26100")
        assert _environment._os_description() == "Windows 11 10.0.26100"

    def test_linux_prefers_the_distribution_name(self, monkeypatch):
        """"Linux 6.8.0-45-generic" and "Ubuntu 24.04.1 LTS" answer different questions, and
        the second is the one that makes a bug reproducible.

        Patched directly rather than through `pretend`: that fixture installs a getter
        returning the value it was given, which for a callable hands back the function instead
        of calling it - and `_os_description` catches `AttributeError`, so the mistake would
        have shown up as the fallback passing for the wrong reason."""
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(platform, "freedesktop_os_release",
                            lambda: {"PRETTY_NAME": "Ubuntu 24.04.1 LTS"})
        monkeypatch.setattr(platform, "release", lambda: "6.8.0-45-generic")
        assert _environment._os_description() == "Ubuntu 24.04.1 LTS"

    @pytest.mark.parametrize("failure, note", [
        pytest.param(OSError("no /etc/os-release"), "minimal image", id="file-absent"),
        pytest.param(AttributeError("freedesktop_os_release"), "python 3.9", id="too-old"),
    ])
    def test_linux_falls_back_to_the_kernel_when_the_distro_cannot_be_read(
            self, monkeypatch, failure, note):
        """`freedesktop_os_release` is 3.10+ and absent on some minimal images. A bug report
        with a kernel version is worth less than one with a distribution; a bug report that
        raised while being assembled is worth nothing."""
        def raise_it():
            raise failure

        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(platform, "freedesktop_os_release", raise_it)
        monkeypatch.setattr(platform, "release", lambda: "6.8.0-45-generic")
        assert _environment._os_description() == "Linux 6.8.0-45-generic"

    def test_a_distro_file_without_a_pretty_name_falls_back_too(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(platform, "freedesktop_os_release", lambda: {"ID": "alpine"})
        monkeypatch.setattr(platform, "release", lambda: "6.6.0")
        assert _environment._os_description() == "Linux 6.6.0"

    def test_an_unrecognised_platform_still_says_something(self, pretend):
        """FreeBSD, or whatever comes next. A report that names an OS this code has never
        heard of is more useful than one that says "unknown"."""
        pretend("FreeBSD", release="14.1-RELEASE")
        assert _environment._os_description() == "FreeBSD 14.1-RELEASE"

    def test_a_platform_that_says_nothing_at_all_is_unknown(self, pretend):
        """`platform.system()` returning "" happens on unusual builds. The empty string would
        render as a blank field beside confident-looking neighbours."""
        pretend("", release="")
        assert _environment._os_description() == "unknown"


class TestPackageVersion:
    def test_an_installed_package_reports_its_version(self):
        assert _environment._package_version("csa-google-workspace") is not None

    def test_a_package_that_is_not_installed_is_none_rather_than_an_error(self):
        """The optional extras. A report assembled on a machine without `mcp` installed has
        to say so in one line, not fail to assemble."""
        assert _environment._package_version("not-a-real-package-b7f2") is None
