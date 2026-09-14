import json

import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.deps import available_readers
from gz_release_dashboard.deps.conda_artifacts import CondaArtifactsReader, pin_floor
from gz_release_dashboard.models import Collection, DependencyRecord, Library

PACKAGES = ("libgz-physics", "libgz-physics7", "libgz-rendering", "libgz-transport")


def url(name):
    return config.ANACONDA_PACKAGE_URL.format(name=name)


@pytest.fixture
def http():
    # libgz-physics9, libgz-rendering10 and libgz-transport15 really are 404:
    # those majors only ever shipped under the unversioned names.
    client = FakeHttpClient()
    for name in PACKAGES:
        client.add(url(name), fixture_text(f"dep-conda-{name}.json"))
    return client


def read(http, *collections):
    return CondaArtifactsReader(http).read(list(collections))


def ordered(records):
    return sorted(records, key=lambda r: (r.collection, r.library, r.major, r.platform, r.declared))


def expected(collection, library, major, rows):
    """The conda records that ``(dependency, platform, declared, version)`` rows stand for."""
    return [
        DependencyRecord(
            collection=collection,
            library=library,
            major=major,
            dependency=dependency,
            system="conda",
            platform=platform,
            declared=declared,
            version=version,
            origin="conda-forge",
        )
        for dependency, platform, declared, version in rows
    ]


def test_the_reader_is_registered_for_conda():
    assert "conda" in available_readers()
    assert CondaArtifactsReader.system == "conda"


def test_the_pins_are_read_from_the_lib_output(http):
    records = read(http, Collection("jetty", False, [Library("gz-physics", 9)]))
    assert ordered(records) == expected(
        "jetty",
        "gz-physics",
        9,
        [
            ("bullet", "linux-64", "bullet-cpp >=3.25,<3.26.0a0", "3.25"),
            ("dart", "linux-64", "dartsim-cpp >=6.19.4,<6.20.0a0", "6.19.4"),
            ("bullet", "osx-arm64", "bullet-cpp >=3.25,<3.26.0a0", "3.25"),
            ("dart", "osx-arm64", "dartsim-cpp >=6.19.4,<6.20.0a0", "6.19.4"),
        ],
    )
    # The 9.3.0 build pinned dartsim-cpp >=6.19.1: an older version never leaks in.
    assert url("libgz-physics") in http.requested
    assert url("gz-physics") not in http.requested


def test_a_build_without_tracked_depends_gives_way_to_the_legacy_name(http):
    # libgz-physics 7.5.0 declares no dart or bullet at all; libgz-physics7
    # 7.5.0 does, so the major is read from the legacy package.
    records = read(http, Collection("harmonic", False, [Library("gz-physics", 7)]))
    assert ordered(records) == expected(
        "harmonic",
        "gz-physics",
        7,
        [
            ("bullet", "linux-64", "bullet-cpp >=3.25,<3.26.0a0", "3.25"),
            ("dart", "linux-64", "dartsim-cpp >=6.19.4,<6.20.0a0", "6.19.4"),
            ("bullet", "osx-arm64", "bullet-cpp >=3.25,<3.26.0a0", "3.25"),
            ("dart", "osx-arm64", "dartsim-cpp >=6.19.4,<6.20.0a0", "6.19.4"),
        ],
    )


def test_the_newest_build_of_a_version_wins_wherever_it_is_listed(http):
    # libgz-physics7 7.5.0 build 0 pinned dartsim-cpp >=6.15.0 and build 7
    # >=6.19.4. The fixture lists build 7 first on linux-64 and last on
    # osx-arm64, so neither the first nor the last entry can be what decides.
    records = read(http, Collection("harmonic", False, [Library("gz-physics", 7)]))
    assert {r.declared for r in records if r.dependency == "dart"} == {
        "dartsim-cpp >=6.19.4,<6.20.0a0"
    }


def test_every_tracked_pin_of_a_build_is_a_declaration(http):
    records = read(http, Collection("jetty", False, [Library("gz-rendering", 10)]))
    assert ordered(records) == expected(
        "jetty",
        "gz-rendering",
        10,
        [
            ("ogre", "linux-64", "ogre >=1.10.12.1,<1.11.0a0", "1.10.12.1"),
            ("ogre-next", "linux-64", "ogre-next >=2.3.3,<2.3.4.0a0", "2.3.3"),
            ("ogre", "linux-aarch64", "ogre >=1.10.12.1,<1.11.0a0", "1.10.12.1"),
            ("ogre-next", "linux-aarch64", "ogre-next >=2.3.3,<2.3.4.0a0", "2.3.3"),
        ],
    )


def test_subdirs_are_reported_separately_so_they_can_disagree(http):
    records = read(http, Collection("jetty", False, [Library("gz-transport", 15)]))
    assert ordered(records) == expected(
        "jetty",
        "gz-transport",
        15,
        [
            ("zenoh", "linux-64", "libzenohc >=1.9.0,<1.9.1.0a0", "1.9.0"),
            ("zenoh", "linux-ppc64le", "libzenohc >=1.2.1,<1.2.2.0a0", "1.2.1"),
        ],
    )


def test_a_pin_repeated_in_one_build_is_one_declaration():
    # libgz-rendering 10.0.0 really lists ogre twice in its depends.
    data = json.loads(fixture_text("dep-conda-libgz-rendering.json"))
    data["files"] = [f for f in data["files"] if f["version"] == "10.0.0"]
    http = FakeHttpClient().add(url("libgz-rendering"), json.dumps(data))
    records = read(http, Collection("jetty", False, [Library("gz-rendering", 10)]))
    assert [(r.platform, r.declared) for r in ordered(records)] == [
        ("linux-64", "ogre >=1.10.12.1,<1.11.0a0"),
        ("linux-64", "ogre-next >=2.3.3,<2.3.4.0a0"),
    ]


def test_a_major_whose_builds_pin_nothing_tracked_has_no_records(http):
    reader = CondaArtifactsReader(http)
    records = reader.read(
        [Collection("ionic", False, [Library("gz-rendering", 9), Library("gz-transport", 14)])]
    )
    assert records == []
    assert reader.errors == []


def test_a_missing_package_is_not_an_error(http):
    reader = CondaArtifactsReader(http)
    records = reader.read([Collection("jetty", False, [Library("gz-nonexistent", 1)])])
    assert records == []
    assert reader.errors == []
    assert http.requested == [url("libgz-nonexistent"), url("libgz-nonexistent1")]


def test_fortress_is_not_read(http):
    records = read(http, Collection("fortress", False, [Library("gz-physics", 9)]))
    assert records == []
    assert http.requested == []


def test_a_library_shared_by_collections_is_recorded_for_each_and_fetched_once(http):
    # Constructed: gz-physics 9 in two collections, the way gz-tools 2 really is.
    records = read(
        http,
        Collection("ionic", False, [Library("gz-physics", 9)]),
        Collection("jetty", False, [Library("gz-physics", 9)]),
        Collection("fortress", False, [Library("gz-physics", 9)]),
    )
    assert {r.collection for r in records} == {"ionic", "jetty"}
    assert len([r for r in records if r.collection == "ionic"]) == 4
    assert len([r for r in records if r.collection == "jetty"]) == 4
    assert http.requested.count(url("libgz-physics")) == 1


def test_conda_name_overrides_apply_before_the_lib_prefix(http, monkeypatch):
    # Synthetic: CONDA_NAME_OVERRIDES is empty today.
    monkeypatch.setitem(config.CONDA_NAME_OVERRIDES, "ignition-transport", "gz-transport")
    records = read(http, Collection("jetty", False, [Library("ignition-transport", 15)]))
    assert {(r.library, r.platform, r.version) for r in records} == {
        ("ignition-transport", "linux-64", "1.9.0"),
        ("ignition-transport", "linux-ppc64le", "1.2.1"),
    }


@pytest.mark.parametrize(
    "spec,floor",
    [
        # The first two are live pins; every other spec is synthetic, since no
        # tracked conda pin is written with ==, a bare version or .* today.
        ("dartsim-cpp >=6.19.4,<6.20.0a0", "6.19.4"),
        ("ogre >=1.10.12.1,<1.11.0a0", "1.10.12.1"),
        ("bullet-cpp <3.26.0a0,>=3.25", "3.25"),
        ("dartsim-cpp ==6.19.4", "6.19.4"),
        ("ogre-next 2.3.3.*", "2.3.3"),
        ("libzenohc 1.9.0", "1.9.0"),
        ("libzenohc 1.9.0 hf35b924_0", "1.9.0"),
        ("ogre <1.11.0a0", None),
        ("mujoco >3.4", None),
        ("dartsim-cpp >=6.19.4|>=7.0", None),
        ("ogre", None),
    ],
)
def test_pin_floor(spec, floor):
    assert pin_floor(spec) == floor
