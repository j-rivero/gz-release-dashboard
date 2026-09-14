import json

import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.deps import create_readers
from gz_release_dashboard.deps.bcr_module import BcrModuleReader
from gz_release_dashboard.models import Collection, DependencyRecord, Library
from gz_release_dashboard.sources.bazel_registry import newest_version
from gz_release_dashboard.versions import GzVersion

#: The registry versions the MODULE.bazel fixtures were captured at, verbatim.
#: The metadata fixtures are live too, trimmed to `versions` and `yanked_versions`.
CAPTURED = (
    ("gz-physics", "9.4.0"),
    ("gz-physics", "8.4.0"),
    ("gz-rendering", "10.0.2"),
    ("gz-transport", "15.1.0"),
)


def metadata_url(module):
    return config.BCR_METADATA_URL.format(module=module)


def module_url(module, version):
    return config.BCR_MODULE_URL.format(module=module, version=version)


@pytest.fixture
def http():
    client = FakeHttpClient()
    for module in sorted({module for module, _ in CAPTURED}):
        client.add(metadata_url(module), fixture_text(f"dep-bazel-{module}-metadata.json"))
    for module, version in CAPTURED:
        client.add(
            module_url(module, version),
            fixture_text(f"dep-bazel-{module}-{version}.MODULE.bazel"),
        )
    return client


def bazel(collection, library, major, dependency, declared, version):
    return DependencyRecord(
        collection=collection,
        library=library,
        major=major,
        dependency=dependency,
        system="bazel",
        platform="all",
        declared=declared,
        version=version,
        origin="bcr",
    )


def read(http, *collections):
    return BcrModuleReader(http).read(list(collections))


def read_synthetic(body, versions=("9.4.0",), yanked=None, raw="9.4.0"):
    """jetty's gz-physics 9, from a synthetic metadata.json and MODULE.bazel ``body``."""
    metadata = {"versions": list(versions), "yanked_versions": yanked or {}}
    http = FakeHttpClient()
    http.add(metadata_url("gz-physics"), json.dumps(metadata))
    http.add(module_url("gz-physics", raw), body)
    return read(http, Collection("jetty", False, [Library("gz-physics", 9)]))


def test_the_newest_version_of_a_major_keeps_the_registry_spelling():
    data = json.loads(fixture_text("bcr-gz-utils.json"))
    # 4.1.0 is yanked; 4.0.0.bcr.1 is the registry's current spelling of 4.0.0.
    assert newest_version(data, 4) == ("4.0.0.bcr.1", GzVersion(4, 0, 0))
    assert newest_version(data, 3) == ("3.1.1", GzVersion(3, 1, 1))
    assert newest_version(data, 5) is None


def test_the_reader_follows_the_bazel_registry_source():
    readers = create_readers(["bazel_registry"], FakeHttpClient())
    assert [type(reader) for reader in readers] == [BcrModuleReader]
    assert readers[0].system == "bazel"


def test_jetty_gz_physics_9_pins_dart_and_bullet(http):
    jetty = Collection("jetty", False, [Library("gz-physics", 9)])
    assert read(http, jetty) == [
        bazel("jetty", "gz-physics", 9, "bullet", "bullet 3.26.0-rc0.bcr.1", "3.26.0"),
        bazel("jetty", "gz-physics", 9, "dart", "dartsim 6.13.2.bcr.3", "6.13.2"),
    ]
    assert http.requested == [
        metadata_url("gz-physics"),
        module_url("gz-physics", "9.4.0"),
    ]


def test_a_pin_is_declared_as_written_and_versioned_without_its_suffixes(http):
    jetty = Collection("jetty", False, [Library("gz-physics", 9)])
    pins = {(r.declared, r.version) for r in read(http, jetty)}
    # `-rc0` and `.bcr.N` both end the upstream version.
    assert pins == {
        ("bullet 3.26.0-rc0.bcr.1", "3.26.0"),
        ("dartsim 6.13.2.bcr.3", "6.13.2"),
    }


def test_jetty_gz_rendering_10_pins_ogre_next(http):
    jetty = Collection("jetty", False, [Library("gz-rendering", 10)])
    assert read(http, jetty) == [
        bazel("jetty", "gz-rendering", 10, "ogre-next", "ogre-next 2.3.3.bcr.6", "2.3.3"),
    ]


def test_gz_transport_pins_no_zenoh(http):
    jetty = Collection("jetty", False, [Library("gz-transport", 15)])
    reader = BcrModuleReader(http)
    # Its protobuf dep carries `repo_name` and matches no alias.
    assert reader.read([jetty]) == []
    assert reader.errors == []


def test_each_major_reads_its_own_newest_module(http):
    # 8.4.0, not 8.3.0.bcr.1, and not the 9.x that is newer still.
    ionic = Collection("ionic", False, [Library("gz-physics", 8)])
    assert read(http, ionic) == [
        bazel("ionic", "gz-physics", 8, "bullet", "bullet 3.26.0-rc0.bcr.1", "3.26.0"),
        bazel("ionic", "gz-physics", 8, "dart", "dartsim 6.13.2.bcr.2", "6.13.2"),
    ]


def test_the_module_is_read_at_the_registrys_own_spelling():
    # Synthetic metadata: 9.4.0 repacked as 9.4.0.bcr.1, under a yanked 9.5.0.
    records = read_synthetic(
        fixture_text("dep-bazel-gz-physics-9.4.0.MODULE.bazel"),
        versions=("9.4.0", "9.4.0.bcr.1", "9.5.0"),
        yanked={"9.5.0": "broken release"},
        raw="9.4.0.bcr.1",
    )
    assert [r.declared for r in records] == ["bullet 3.26.0-rc0.bcr.1", "dartsim 6.13.2.bcr.3"]


def test_a_multi_line_bazel_dep_with_a_repo_name_is_read():
    # Synthetic, laid out like protobuf 30.1's abseil-py dep: no gz module
    # splits a tracked pin over several lines today.
    body = (
        'bazel_dep(name = "bazel_skylib", version = "1.7.1")\n'
        "bazel_dep(\n"
        '    name = "dartsim",\n'
        '    version = "6.13.2.bcr.3",\n'
        '    repo_name = "dart",\n'
        ")\n"
    )
    assert read_synthetic(body) == [
        bazel("jetty", "gz-physics", 9, "dart", "dartsim 6.13.2.bcr.3", "6.13.2"),
    ]


def test_a_dev_dependency_is_not_a_declaration():
    # Synthetic, spelled as protobuf 30.1 and rules_cc 0.2.0 spell their test deps.
    body = (
        'bazel_dep(name = "bullet", version = "3.26.0-rc0.bcr.1", dev_dependency = True)\n'
        "bazel_dep(\n"
        '    name = "ogre-next",\n'
        '    version = "2.3.3.bcr.6",\n'
        "    dev_dependency = True,\n"
        ")\n"
        'bazel_dep(name = "dartsim", version = "6.13.2.bcr.3")\n'
    )
    assert read_synthetic(body) == [
        bazel("jetty", "gz-physics", 9, "dart", "dartsim 6.13.2.bcr.3", "6.13.2"),
    ]


def test_a_commented_out_bazel_dep_is_not_a_declaration():
    # Synthetic: an engine left in the file but switched off.
    body = (
        '# bazel_dep(name = "mujoco", version = "3.3.0")\n'
        'bazel_dep(name = "dartsim", version = "6.13.2.bcr.3")\n'
    )
    assert read_synthetic(body) == [
        bazel("jetty", "gz-physics", 9, "dart", "dartsim 6.13.2.bcr.3", "6.13.2"),
    ]


def test_a_bazel_dep_without_a_version_is_declared_but_unresolved():
    # Synthetic: Bazel lets a dep omit its version when an override supplies it.
    body = 'bazel_dep(name = "dartsim")\n'
    assert read_synthetic(body) == [
        bazel("jetty", "gz-physics", 9, "dart", "dartsim", None),
    ]


def test_a_module_missing_from_the_registry_yields_no_records():
    http = FakeHttpClient()  # every ok_404 request is a 404
    reader = BcrModuleReader(http)
    assert reader.read([Collection("jetty", False, [Library("gz-jetty", 1)])]) == []
    assert reader.errors == []


def test_a_missing_module_file_yields_no_records():
    # Synthetic metadata naming a version whose MODULE.bazel is not served.
    http = FakeHttpClient().add(metadata_url("gz-physics"), json.dumps({"versions": ["9.4.0"]}))
    reader = BcrModuleReader(http)
    assert reader.read([Collection("jetty", False, [Library("gz-physics", 9)])]) == []
    assert reader.errors == []
    assert module_url("gz-physics", "9.4.0") in http.requested


def test_a_major_the_registry_never_published_yields_no_records(http):
    m = Collection("m", True, [Library("gz-physics", 10)])
    assert read(http, m) == []
    assert http.requested == [metadata_url("gz-physics")]


def test_libraries_bcr_never_ships_are_not_asked_for():
    http = FakeHttpClient()
    jetty = Collection(
        "jetty", False, [Library("gz-cmake", 5), Library("gz-tools", 2), Library("gz-gui", 10)]
    )
    assert read(http, jetty) == []
    assert http.requested == []


def test_collections_bcr_does_not_publish_are_skipped(http):
    fortress = Collection("fortress", False, [Library("gz-physics", 5)])
    harmonic = Collection("harmonic", False, [Library("gz-physics", 7)])
    assert read(http, fortress, harmonic) == []
    assert http.requested == []


def test_a_major_shared_by_collections_is_recorded_for_each(http):
    # Synthetic sharing: the majors really shared today (gz-tools 2) have no module.
    jetty = Collection("jetty", False, [Library("gz-physics", 9)])
    m = Collection("m", True, [Library("gz-physics", 9)])
    assert [(r.collection, r.dependency) for r in read(http, jetty, m)] == [
        ("jetty", "bullet"),
        ("jetty", "dart"),
        ("m", "bullet"),
        ("m", "dart"),
    ]
