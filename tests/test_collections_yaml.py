from conftest import fixture_text

from gz_release_dashboard.collections_yaml import (
    linux_distros,
    load_collections,
    parse_collections,
)
from gz_release_dashboard.models import Library


def names(collections):
    return [c.name for c in collections]


def test_rotary_is_dropped(collections):
    assert "rotary" not in names(collections)


def test_released_and_development_collections_are_kept(collections):
    assert names(collections) == ["fortress", "jetty", "m"]


def test_collection_with_no_ci_configs_is_in_development(collections):
    by_name = {c.name: c for c in collections}
    assert by_name["m"].in_development is True
    assert by_name["jetty"].in_development is False
    assert by_name["fortress"].in_development is False


def test_metapackages_are_excluded(collections):
    every_lib = {lib.name for c in collections for lib in c.libraries}
    assert "gz-jetty" not in every_lib
    assert "gz-fortress" not in every_lib
    assert "gz-rotary" not in every_lib


def test_libraries_carry_their_major_version(collections):
    by_name = {c.name: c for c in collections}
    assert Library("gz-sim", 10) in by_name["jetty"].libraries
    assert Library("sdformat", 16) in by_name["jetty"].libraries
    assert Library("gz-sim", 6) in by_name["fortress"].libraries


def test_libs_without_a_major_version_are_dropped():
    text = """
collections:
  - name: unreleased
    libs:
      - {name: gz-sim, repo: {current_branch: main}}
    ci: {configs: [noble]}
"""
    assert parse_collections(text) == []


def test_ignore_list_is_overridable():
    text = fixture_text("gz-collections.yaml")
    assert names(parse_collections(text, ignored=("jetty", "rotary"))) == ["fortress", "m"]


def test_load_collections_uses_the_configured_url(http):
    from gz_release_dashboard import config

    http.add(config.COLLECTIONS_YAML_URL, fixture_text("gz-collections.yaml"))
    assert names(load_collections(http)) == ["fortress", "jetty", "m"]


def test_each_collection_records_the_linux_releases_it_packages_for(collections):
    by_name = {c.name: c for c in collections}
    assert by_name["fortress"].distros == ["jammy"]
    assert by_name["jetty"].distros == ["noble"]
    assert by_name["m"].distros == ["resolute"]


def test_macos_configs_are_not_mistaken_for_a_distro(collections):
    # brew_arm64 is so=darwin, version=all; it has no distro axis.
    assert all("all" not in c.distros for c in collections)


def test_end_of_life_releases_drop_out_by_themselves(collections):
    # focal is absent because no live collection packages for it any more,
    # not because anything here names it.
    distros = linux_distros(collections)
    assert distros == ("jammy", "noble", "resolute")
    assert "focal" not in distros


def test_the_distro_list_is_the_union_never_a_per_collection_filter(collections):
    # jetty declares only noble upstream, yet ships on resolute too, so the
    # union is the only trustworthy reading of these declarations.
    assert "resolute" in linux_distros(collections)
    jetty = next(c for c in collections if c.name == "jetty")
    assert "resolute" not in jetty.distros


def test_an_ignored_collection_cannot_resurrect_a_distro():
    text = fixture_text("gz-collections.yaml")
    only_m = parse_collections(text, ignored=("rotary", "fortress", "jetty"))
    assert linux_distros(only_m) == ("resolute",)


def test_distros_stay_in_chronological_declaration_order(collections):
    assert list(linux_distros(collections)) == sorted(
        linux_distros(collections), key=["jammy", "noble", "resolute"].index
    )
