import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.models import Collection, Library
from gz_release_dashboard.sources.conda_forge import CondaForgeSource, subdir_arch


def url(name):
    return config.ANACONDA_PACKAGE_URL.format(name=name)


@pytest.fixture
def http():
    client = FakeHttpClient()
    client.add(url("gz-sim"), fixture_text("conda-gz-sim.json"))
    client.add(url("gz-sim9"), fixture_text("conda-gz-sim9-legacy.json"))
    client.add(url("gz-cmake"), fixture_text("conda-gz-cmake.json"))
    return client


@pytest.fixture
def collections():
    return [
        Collection("ionic", False, [Library("gz-sim", 9), Library("gz-cmake", 4)]),
        Collection("jetty", False, [Library("gz-sim", 10), Library("gz-cmake", 5)]),
    ]


@pytest.fixture
def records(http, collections):
    return CondaForgeSource(http).fetch(collections)


def indexed(records):
    return {(r.library, r.major, r.platform): r for r in records}


@pytest.mark.parametrize(
    "subdir,arch",
    [
        ("linux-64", "x86_64"),
        ("osx-64", "x86_64"),
        ("win-64", "x86_64"),
        ("linux-aarch64", "aarch64"),
        ("osx-arm64", "arm64"),
        ("linux-ppc64le", "ppc64le"),
    ],
)
def test_subdir_arch(subdir, arch):
    assert subdir_arch(subdir) == arch


def test_one_feedstock_serves_every_major(http, collections):
    CondaForgeSource(http).fetch(collections)
    assert http.requested.count(url("gz-sim")) == 1


def test_a_mixed_major_feedstock_is_filtered_per_major(records):
    entries = indexed(records)
    assert entries[("gz-sim", 10, "linux-64")].upstream_version == "10.5.0"
    # 10.5.0 is the feedstock's latest_version but must not leak into major 9.
    assert entries[("gz-sim", 9, "osx-arm64")].upstream_version == "9.5.0"


def test_a_legacy_feedstock_that_is_ahead_wins(records):
    entry = indexed(records)[("gz-sim", 9, "linux-64")]
    assert entry.upstream_version == "9.6.0"
    assert entry.pkg_name == "gz-sim9"


def test_versions_are_reported_per_subdir(records):
    platforms = {r.platform for r in records if (r.library, r.major) == ("gz-sim", 9)}
    assert platforms == {"linux-64", "osx-arm64", "linux-ppc64le"}


def test_files_without_a_subdir_or_a_sane_version_are_skipped(records):
    assert all(r.platform for r in records)
    assert "win-64" not in {r.platform for r in records}


def test_a_feedstock_with_no_file_detail_falls_back_to_the_version_list(records):
    entries = indexed(records)
    assert entries[("gz-cmake", 4, "all")].upstream_version == "4.2.0"
    assert entries[("gz-cmake", 5, "all")].upstream_version == "5.1.1"
    assert entries[("gz-cmake", 5, "all")].arch == "all"


def test_a_missing_feedstock_is_not_an_error(http):
    records = CondaForgeSource(http).fetch(
        [Collection("jetty", False, [Library("gz-nonexistent", 1)])]
    )
    assert records == []


def test_candidate_names_try_the_unversioned_feedstock_first():
    assert CondaForgeSource.candidate_names("gz-sim", 9) == ["gz-sim", "gz-sim9"]
    assert CondaForgeSource.candidate_names("sdformat", 16) == ["sdformat", "sdformat16"]
