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
    sdf = by_library(records, "prerelease")["sdformat"]
    assert sdf.raw_version == "16.2.0~pre1-1~noble"
    assert sdf.upstream_version == "16.2.0-pre1"


def test_only_prereleases_ahead_of_stable_survive(records):
    """The two repositories are enabled together, so apt takes the higher one.

    sdformat 16.2.0-pre1 beats the 16.1.0 in stable and is a pending release.
    gz-sim 10.0.0-pre1 lost to 10.5.0 long ago and gz-math ties its own stable
    version: neither is installable, and both are history, not news.
    """
    assert set(by_library(records, "prerelease")) == {"sdformat"}


def test_a_released_major_buries_its_candidates_on_every_architecture(jetty):
    """The case that survives a per-architecture comparison and should not.

    Stable never built sdformat 16 for i386, so nothing there outranks an old
    candidate sitting on i386 -- but 16.1.0 shipped on amd64, which makes
    16.0.0-pre1 a past release wherever it lingers. This is real: harmonic still
    has gz-msgs10 10.0.0-pre3 on jammy/i386, three minors after 10.4.0.
    """
    http = FakeHttpClient()
    http.add_gzip(url("stable", "noble", "amd64"), fixture_text("osrf-packages-stable.txt"))
    http.add_gzip(
        url("prerelease", "noble", "i386"),
        "Package: libsdformat16\nSource: sdformat16\n"
        "Version: 16.0.0~pre1-1~noble\nArchitecture: i386\nSection: libs\n",
    )
    records = OsrfDebianSource(http).fetch(jetty)
    assert by_library(records, "prerelease") == {}


def test_a_prerelease_with_no_stable_counterpart_survives(jetty):
    """The state of an in-development collection: staged, never released."""
    http = FakeHttpClient()
    http.add_gzip(
        url("prerelease", "noble", "amd64"), fixture_text("osrf-packages-prerelease.txt")
    )
    records = OsrfDebianSource(http).fetch(jetty)
    assert by_library(records, "prerelease").keys() == {"gz-sim", "gz-math", "sdformat"}


def test_libraries_outside_the_collections_are_dropped(jetty):
    http = FakeHttpClient()
    http.add_gzip(url("stable", "noble", "amd64"), fixture_text("osrf-packages-stable.txt"))
    # sdformat 16 is a jetty library; drop it and its records must vanish too.
    jetty[0].libraries = [Library("gz-sim", 10)]
    records = OsrfDebianSource(http).fetch(jetty)
    assert {r.library for r in records} == {"gz-sim"}


def test_only_the_declared_linux_releases_are_queried(jetty):
    http = FakeHttpClient()
    http.add_gzip(url("stable", "noble", "amd64"), fixture_text("osrf-packages-stable.txt"))
    jetty[0].distros = ["noble", "resolute"]
    OsrfDebianSource(http).fetch(jetty)
    queried = {u.split("/dists/")[1].split("/")[0] for u in http.requested}
    assert queried == {"noble", "resolute"}
    # focal is end of life: no collection declares it, so it is never fetched.
    assert not any("focal" in u for u in http.requested)


def test_the_configured_matrix_is_only_a_fallback(jetty):
    http = FakeHttpClient()
    jetty[0].distros = []
    OsrfDebianSource(http).fetch(jetty)
    queried = {u.split("/dists/")[1].split("/")[0] for u in http.requested}
    assert queried == set(config.OSRF_DEB_DISTROS)


def test_i386_is_never_queried(jetty):
    """Gazebo does not support i386; what is left in the index is a leftover."""
    http = FakeHttpClient()
    OsrfDebianSource(http).fetch(jetty)
    assert not [u for u in http.requested if "binary-i386" in u]


def test_armhf_is_queried_only_where_it_is_published(jetty):
    """armhf stops after noble. Asking resolute for it is 404 noise, and a
    leftover package found there would read as evidence the architecture is
    built -- which is exactly what turns a deliberate drop into a reported gap.
    """
    http = FakeHttpClient()
    OsrfDebianSource(http).fetch(jetty)
    armhf = {u.split("/dists/")[1].split("/")[0] for u in http.requested
             if "binary-armhf" in u}
    assert armhf == {"jammy", "noble"}
    amd64 = {u.split("/dists/")[1].split("/")[0] for u in http.requested
             if "binary-amd64" in u}
    assert "resolute" in amd64


def test_deb_arches_leaves_unlisted_architectures_everywhere():
    assert config.deb_arches("jammy") == ("amd64", "arm64", "armhf")
    assert config.deb_arches("noble") == ("amd64", "arm64", "armhf")
    assert config.deb_arches("resolute") == ("amd64", "arm64")
    # A release nobody has heard of yet still gets the unrestricted set.
    assert config.deb_arches("swift") == ("amd64", "arm64")
