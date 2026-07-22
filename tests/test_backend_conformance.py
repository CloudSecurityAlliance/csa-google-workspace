"""Seam guard: FakeBackend and ApiBackend must both satisfy the Backend Protocol with
matching method signatures (audit #14).

FakeBackend powers every unit test, so if a new Backend method is added to ApiBackend (or
the Protocol) but not FakeBackend — or a signature drifts — unit tests would exercise a
stale fake. This test fails loudly on that drift. (Behavioral parity for the real-Google
paths, e.g. error translation, is covered separately in test_apibackend_*.)
"""
import inspect

import pytest

from csa_google_workspace.backend import ApiBackend, Backend, FakeBackend


def _protocol_methods() -> set[str]:
    return {name for name, val in vars(Backend).items()
            if callable(val) and not name.startswith("_")}


def _params(func) -> list[tuple[str, bool]]:
    """(name, has_default) for each parameter except self — annotations ignored, since the
    Protocol is annotated and the concrete impls need not be."""
    sig = inspect.signature(func)
    return [(p.name, p.default is not inspect.Parameter.empty)
            for p in sig.parameters.values() if p.name != "self"]


def test_protocol_has_the_expected_surface():
    # sanity: catch accidental emptiness of the introspection
    methods = _protocol_methods()
    assert {"get_file_metadata", "list_comments", "create_comment",
            "sheets_values_append", "slides_batch_update"} <= methods


@pytest.mark.parametrize("impl", [FakeBackend, ApiBackend], ids=["FakeBackend", "ApiBackend"])
def test_impl_covers_protocol_with_matching_signatures(impl):
    for name in sorted(_protocol_methods()):
        assert hasattr(impl, name), f"{impl.__name__} is missing Backend.{name}"
        want = _params(getattr(Backend, name))
        got = _params(getattr(impl, name))
        assert got == want, f"{impl.__name__}.{name} params {got} != Protocol {want}"
