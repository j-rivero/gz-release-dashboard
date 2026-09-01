import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.models import Collection, Library
from gz_release_dashboard.sources.homebrew import (
    HomebrewSource,
    bottle_labels,
    formula_names,
    label_arch,
)


def url(formula):
    return config.HOMEBREW_FORMULA_URL.format(formula=formula)


@pytest.fixture
def http():
    client = FakeHttpClient()
    client.add(url("gz-sim10"), fixture_text("brew-gz-sim10.rb"))
    client.add(url("gz-fuel-tools11"), fixture_text("brew-gz-fuel-tools11.rb"))
    client.add(url("ignition-tools"), fixture_text("brew-ignition-tools.rb"))
    client.add(url("gz-jetty"), fixture_text("brew-gz-jetty.rb"))
    client.add(url("gz-rotary-sim"), fixture_text("brew-gz-rotary-sim.rb"))
    return client


@pytest.fixture
def collections():
    return [
        Collection(
            "jetty", False,
            [Library("gz-sim", 10), Library("gz-fuel-tools", 11), Library("gz-tools", 1)],
        )
    ]


@pytest.fixture
def records(http, collections):
    return HomebrewSource(http).fetch(collections)


def test_formula_names_follow_the_naming_eras():
    assert formula_names("gz-sim", 10)[0] == "gz-sim10"
    assert "ignition-gazebo6" in formula_names("gz-sim", 6)
    # gz-plugin 1's formula is `ignition-plugin1`, though its tags are unsuffixed.
    assert "ignition-plugin1" in formula_names("gz-plugin", 1)
    assert "ignition-tools" in formula_names("gz-tools", 1)


@pytest.mark.parametrize(
    "label,arch",
    [("arm64_sequoia", "arm64"), ("arm64_sonoma", "arm64"), ("sonoma", "x86_64"),
     ("ventura", "x86_64")],
)
def test_label_arch(label, arch):
    assert label_arch(label) == arch


def test_bottle_labels_are_read_without_hardcoding_codenames():
    assert bottle_labels(fixture_text("brew-gz-sim10.rb")) == [
        "arm64_sequoia", "arm64_sonoma", "sonoma",
    ]


def test_the_cellar_prefix_does_not_hide_the_label():
    assert bottle_labels(fixture_text("brew-gz-fuel-tools11.rb")) == [
        "arm64_sequoia", "arm64_sonoma", "sonoma",
    ]
    assert bottle_labels(fixture_text("brew-ignition-tools.rb")) == [
        "arm64_sonoma", "ventura",
    ]


def test_a_formula_with_no_bottle_block_has_no_labels():
    assert bottle_labels(fixture_text("brew-gz-jetty.rb")) == []


def test_one_record_per_bottle(records):
    sim = [r for r in records if r.library == "gz-sim"]
    assert {r.platform for r in sim} == {"arm64_sequoia", "arm64_sonoma", "sonoma"}
    assert {r.arch for r in sim} == {"arm64", "x86_64"}


def test_the_packaging_revision_rides_in_the_raw_version(records):
    sim = next(r for r in records if r.library == "gz-sim")
    assert sim.raw_version == "10.5.0_10"
    assert sim.upstream_version == "10.5.0"


def test_a_tarball_named_unlike_its_formula_still_yields_a_version(records):
    # gz-fuel-tools11 ships `gz-fuel_tools-11.0.0.tar.bz2`, with an underscore.
    fuel = next(r for r in records if r.library == "gz-fuel-tools")
    assert fuel.upstream_version == "11.0.0"
    assert fuel.raw_version == "11.0.0_34"


def test_the_ignition_era_formula_is_found_by_falling_back(records, http):
    tools = [r for r in records if r.library == "gz-tools"]
    assert tools and tools[0].pkg_name == "ignition-tools"
    assert tools[0].upstream_version == "1.5.0"
    # It only got there after the suffixed candidates 404'd.
    assert url("gz-tools1") in http.requested


def test_a_formula_without_a_url_yields_nothing(http):
    # gz-rotary-* formulas track a branch head, so they have no release version.
    records = HomebrewSource(http).fetch(
        [Collection("rotary", False, [Library("gz-rotary-sim", 1)])]
    )
    assert records == []


def test_a_library_with_no_formula_at_all_is_skipped(http):
    records = HomebrewSource(http).fetch(
        [Collection("m", True, [Library("gz-sim", 11)])]
    )
    assert records == []


def test_a_formula_whose_version_contradicts_the_major_is_rejected(http):
    # `gz-jetty.rb` is at 1.0.0; asking for major 2 must not accept it.
    records = HomebrewSource(http).fetch(
        [Collection("jetty", False, [Library("gz-jetty", 2)])]
    )
    assert records == []
