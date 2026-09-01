from conftest import fixture_text

from gz_release_dashboard.collections_yaml import load_collections, parse_collections
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
