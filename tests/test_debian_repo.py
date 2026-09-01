from conftest import fixture_text

from gz_release_dashboard.sources.debian_repo import (
    canonical_library,
    packages_url,
    parse_stanzas,
    source_name,
    split_source_name,
)


def test_stanzas_are_split_on_blank_lines():
    stanzas = list(parse_stanzas(fixture_text("osrf-packages-stable.txt")))
    assert len(stanzas) == 11
    assert stanzas[0]["Package"] == "libgz-sim10-dev"


def test_folded_continuation_lines_stay_with_their_field():
    stanza = next(iter(parse_stanzas(fixture_text("osrf-packages-stable.txt"))))
    assert stanza["Description"].startswith("Gazebo Sim classes")
    assert "designed to rapidly develop robot applications." in stanza["Description"]
    assert "Gazebo Sim is a component" in stanza["Description"]


def test_source_defaults_to_package_and_drops_the_version():
    assert source_name({"Package": "ignition-tools"}) == "ignition-tools"
    assert source_name({"Package": "libgz-sim10", "Source": "gz-sim10 (10.5.0-2~noble)"}) == "gz-sim10"


def test_canonical_library_renames_the_ignition_era():
    assert canonical_library("ignition-gazebo") == "gz-sim"
    assert canonical_library("ignition-fuel-tools") == "gz-fuel-tools"
    assert canonical_library("gz-sim") == "gz-sim"
    assert canonical_library("sdformat") == "sdformat"


def test_split_source_name():
    assert split_source_name("gz-sim10") == ("gz-sim", 10)
    assert split_source_name("gz-fuel-tools10") == ("gz-fuel-tools", 10)
    assert split_source_name("ignition-gazebo6") == ("gz-sim", 6)
    assert split_source_name("sdformat16") == ("sdformat", 16)


def test_an_unsuffixed_source_is_major_one():
    # `ignition-tools` and `ignition-plugin` never carried a suffix.
    assert split_source_name("ignition-tools") == ("gz-tools", 1)
    assert split_source_name("ignition-plugin") == ("gz-plugin", 1)


def test_names_that_are_not_gz_libraries_are_rejected():
    assert split_source_name("dart6.13") is None
    assert split_source_name("blender-ogrexml-next-2.3") is None


def test_packages_url():
    assert packages_url("http://x/gazebo", "ubuntu-stable", "noble", "amd64") == (
        "http://x/gazebo/ubuntu-stable/dists/noble/main/binary-amd64/Packages.gz"
    )
