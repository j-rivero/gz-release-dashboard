import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.models import Collection, Library
from gz_release_dashboard.sources.bazel_registry import BazelRegistrySource


def url(module):
    return config.BCR_METADATA_URL.format(module=module)


@pytest.fixture
def http():
    client = FakeHttpClient()
    client.add(url("gz-utils"), fixture_text("bcr-gz-utils.json"))
    client.add(url("gz-sim"), fixture_text("bcr-gz-sim.json"))
    return client


@pytest.fixture
def collections():
    return [
        Collection("ionic", False, [Library("gz-utils", 3), Library("gz-sim", 9)]),
        Collection(
            "jetty", False,
            [Library("gz-utils", 4), Library("gz-sim", 10), Library("gz-gui", 10)],
        ),
    ]


@pytest.fixture
def records(http, collections):
    return {
        (r.library, r.major): r for r in BazelRegistrySource(http).fetch(collections)
    }


def test_one_module_serves_every_major(http, collections):
    BazelRegistrySource(http).fetch(collections)
    assert http.requested.count(url("gz-utils")) == 1


def test_versions_are_filtered_by_major(records):
    assert records[("gz-utils", 3)].upstream_version == "3.1.1"
    assert records[("gz-utils", 4)].upstream_version == "4.0.0"


def test_the_bcr_repack_suffix_is_stripped(records):
    entry = records[("gz-utils", 4)]
    assert entry.raw_version == "4.0.0.bcr.1"
    assert entry.upstream_version == "4.0.0"


def test_yanked_versions_are_ignored(records):
    # 4.1.0 is the highest 4.x but it was yanked.
    assert records[("gz-utils", 4)].upstream_version == "4.0.0"


def test_a_prerelease_never_outranks_its_own_release(records):
    assert records[("gz-utils", 4)].upstream_version == "4.0.0"


def test_modules_absent_from_the_registry_yield_no_records(records):
    assert ("gz-gui", 10) not in records


def test_records_are_flat_with_no_platform_axis(records):
    entry = records[("gz-sim", 10)]
    assert (entry.channel, entry.platform, entry.arch) == ("", "all", "all")
    assert entry.upstream_version == "10.5.0"


def test_expected_absent_covers_the_libraries_bcr_never_ships():
    assert config.EXPECTED_ABSENT["bazel_registry"] == frozenset(
        {"gz-cmake", "gz-tools", "gz-gui", "gz-launch"}
    )
