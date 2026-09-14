import pytest

from conftest import FakeHttpClient

from gz_release_dashboard import deps
from gz_release_dashboard.deps.base import DependencyReader


@pytest.fixture
def registry(monkeypatch):
    """An empty registry, so these tests see only the readers they register."""
    monkeypatch.setattr(deps, "_REGISTRY", {})


def reader(system_name):
    class Reader(DependencyReader):
        system = system_name

        def read(self, collections):
            return []

    Reader.__name__ = f"{system_name.title()}Reader"
    return Reader


def test_readers_follow_the_library_sources_that_were_selected(registry):
    deps.register_reader(reader("conda"))
    deps.register_reader(reader("deb"))
    created = deps.create_readers(["conda_forge"], FakeHttpClient())
    assert [r.system for r in created] == ["conda"]


def test_every_reader_runs_when_no_source_was_selected(registry):
    deps.register_reader(reader("conda"))
    deps.register_reader(reader("deb"))
    assert [r.system for r in deps.create_readers(None, FakeHttpClient())] == ["conda", "deb"]


def test_a_reader_for_a_system_config_does_not_know_is_refused(registry):
    with pytest.raises(ValueError, match="pip"):
        deps.register_reader(reader("pip"))


def test_two_readers_for_one_system_are_refused(registry):
    deps.register_reader(reader("conda"))
    with pytest.raises(ValueError, match="conda"):
        deps.register_reader(reader("conda"))
