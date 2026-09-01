import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.models import Collection, Library
from gz_release_dashboard.sources.debian_repo import packages_url
from gz_release_dashboard.sources.osrf_debian import OsrfDebianSource


def url(channel, distro, arch):
    return packages_url(
        config.OSRF_DEB_BASE, config.OSRF_DEB_CHANNELS[channel], distro, arch
    )


@pytest.fixture
def jetty():
    return [
        Collection(
            "jetty",
            False,
            [
                Library("gz-sim", 10),
                Library("gz-gui", 10),
                Library("gz-math", 9),
                Library("sdformat", 16),
                Library("gz-tools", 1),
            ],
        )
    ]


@pytest.fixture
def records(jetty):
    http = FakeHttpClient()
    http.add_gzip(url("stable", "noble", "amd64"), fixture_text("osrf-packages-stable.txt"))
    http.add_gzip(
        url("prerelease", "noble", "amd64"), fixture_text("osrf-packages-prerelease.txt")
    )
    return OsrfDebianSource(http).fetch(jetty)


def by_library(records, channel="stable"):
    return {r.library: r for r in records if r.channel == channel}


def test_missing_distro_arch_combinations_are_skipped(records):
    # Only two of the 32 matrix URLs were served; the rest 404 harmlessly.
    assert {(r.channel, r.platform, r.arch) for r in records} == {
        ("stable", "noble", "amd64"),
        ("prerelease", "noble", "amd64"),
    }


def test_split_binary_packages_collapse_to_one_record_per_library(records):
    sim = [r for r in records if r.library == "gz-sim" and r.channel == "stable"]
    assert len(sim) == 1
    assert sim[0].upstream_version == "10.5.0"
    assert sim[0].pkg_name == "gz-sim10"


def test_the_newest_version_wins(records):
    # gz-math9 appears at 9.2.0 and 9.3.0 in the same index.
    assert by_library(records)["gz-math"].upstream_version == "9.3.0"


def test_debug_symbol_packages_are_ignored(records):
    assert all("dbgsym" not in r.pkg_name for r in records)


def test_alias_metapackages_do_not_become_records(records):
    assert all(not r.pkg_name.startswith("gz-jetty-") for r in records)


def test_non_gazebo_packages_are_filtered_out(records):
    assert "dart6.13" not in {r.library for r in records}
    assert "dart" not in {r.library for r in records}


def test_the_collection_metapackage_is_filtered_out(records):
    assert "gz-jetty" not in {r.library for r in records}


def test_a_package_with_no_major_suffix_maps_to_major_one(records):
    tools = by_library(records)["gz-tools"]
    assert (tools.library, tools.major) == ("gz-tools", 1)
    assert tools.upstream_version == "1.5.0"


def test_the_995_packaging_revision_is_stripped(records):
    gui = by_library(records)["gz-gui"]
    assert gui.raw_version == "10.1.1-1.995~noble"
    assert gui.upstream_version == "10.1.1"


def test_a_staged_prerelease_keeps_its_pre_suffix(records):
    sim = by_library(records, "prerelease")["gz-sim"]
    assert sim.raw_version == "10.0.0~pre1-1~noble"
    assert sim.upstream_version == "10.0.0-pre1"


def test_libraries_outside_the_collections_are_dropped(jetty):
    http = FakeHttpClient()
    http.add_gzip(url("stable", "noble", "amd64"), fixture_text("osrf-packages-stable.txt"))
    # sdformat 16 is a jetty library; drop it and its records must vanish too.
    jetty[0].libraries = [Library("gz-sim", 10)]
    records = OsrfDebianSource(http).fetch(jetty)
    assert {r.library for r in records} == {"gz-sim"}
