from collections import Counter

import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.deps import available_readers
from gz_release_dashboard.deps.brew_formula import (
    BrewFormulaReader,
    declared_dependencies,
    tap_version,
)
from gz_release_dashboard.models import Collection, DependencyRecord, FetchError, Library

#: Captured 2026-09-14 from osrf/homebrew-simulation, each trimmed to the part
#: of the formula above `def install` (or its first patch): what gets read.
TAP_FIXTURES = (
    "gz-rendering10", "gz-physics9", "ignition-rendering6", "sdformat9", "gz-rotary-physics",
    "ogre2.3", "ogre2.2", "ogre1.9", "dartsim@6.10.0", "bullet@2.87",
)
#: Captured the same day from formulae.brew.sh, trimmed to the top-level keys
#: that identify the formula plus `versions`.
CORE_FIXTURES = ("dartsim", "bullet")
#: The bottles of gz-rendering10 and ignition-rendering6.
THREE_BOTTLES = ("arm64_sequoia", "arm64_sonoma", "sonoma")
#: The bottles of gz-physics9.
TWO_BOTTLES = ("arm64_sequoia", "arm64_sonoma")


def tap(formula):
    return config.HOMEBREW_FORMULA_URL.format(formula=formula)


def core(formula):
    return config.HOMEBREW_CORE_FORMULA_URL.format(formula=formula)


@pytest.fixture
def http():
    client = FakeHttpClient()
    for formula in TAP_FIXTURES:
        client.add(tap(formula), fixture_text(f"dep-brew-{formula}.rb"))
    for formula in CORE_FIXTURES:
        client.add(core(formula), fixture_text(f"dep-brew-core-{formula}.json"))
    return client


def test_the_reader_is_registered_for_brew():
    assert BrewFormulaReader.system == "brew"
    assert "brew" in available_readers()


def test_build_and_test_only_dependencies_are_not_declared():
    # `cmake` and `pkgconf` are `=> [:build, :test]`, `gz-plugin2` is `=> :test`.
    assert declared_dependencies(fixture_text("dep-brew-ignition-rendering6.rb")) == [
        "freeimage", "ignition-cmake2", "ignition-common4", "ignition-math6",
        "ignition-plugin1", "ignition-utils1", "ogre1.9", "ogre2.2",
    ]
    # `cmake` is `=> :build`.
    assert declared_dependencies(fixture_text("dep-brew-ogre2.3.rb")) == [
        "doxygen", "freeimage", "freetype", "libx11", "libzzip", "rapidjson", "tbb",
    ]


@pytest.mark.parametrize(
    "formula,raw",
    [
        # A GitHub tag archive, with and without the `v`.
        ("ogre2.3", "2.3.1"),
        ("bullet@2.87", "2.87"),
        # A commit tarball, so the version is stated, in three spellings.
        ("ogre2.2", "2.2.6+20211021~312bf40"),
        ("ogre1.9", "1.9-20160714-108ab0bcc69603dba32c0ffd4bbbc39051f421c9"),
        ("dartsim@6.10.0", "6.10.0~20211005~d2b6ee08a60d0dbf71b0f008cd8fed1f611f6e24"),
        # The `<name>-X.Y.Z.tar.*` release tarball the gz formulas use.
        ("gz-rendering10", "10.0.2"),
    ],
)
def test_tap_version_spellings(formula, raw):
    assert tap_version(fixture_text(f"dep-brew-{formula}.rb")) == raw


def test_a_stated_version_wins_over_the_url():
    # Synthetic: no live formula states a version its url also carries.
    text = (
        'url "https://github.com/OGRECave/ogre-next/archive/refs/tags/v2.3.1.tar.gz"\n'
        'version "2.3.3"\n'
    )
    assert tap_version(text) == "2.3.3"


def test_jetty_gz_rendering10_declares_ogre_1_9_and_ogre_2_3_from_the_tap(http):
    jetty = Collection("jetty", False, [Library("gz-rendering", 10)])
    records = BrewFormulaReader(http).read([jetty])
    assert records == [
        DependencyRecord("jetty", "gz-rendering", 10, "ogre", "brew", label, "ogre1.9", "1.9", "tap")
        for label in THREE_BOTTLES
    ] + [
        DependencyRecord(
            "jetty", "gz-rendering", 10, "ogre-next", "brew", label, "ogre2.3", "2.3.1", "tap"
        )
        for label in THREE_BOTTLES
    ]


def test_fortress_finds_the_ignition_era_formula_and_its_ogre_2_2(http):
    fortress = Collection("fortress", False, [Library("gz-rendering", 6)])
    records = BrewFormulaReader(http).read([fortress])
    assert {(r.declared, r.version, r.origin) for r in records} == {
        ("ogre1.9", "1.9", "tap"),
        ("ogre2.2", "2.2.6", "tap"),
    }
    assert {r.platform for r in records} == set(THREE_BOTTLES)
    assert http.requested.index(tap("gz-rendering6")) < http.requested.index(
        tap("ignition-rendering6")
    )


def test_jetty_gz_physics9_resolves_dartsim_and_bullet_through_homebrew_core(http):
    jetty = Collection("jetty", False, [Library("gz-physics", 9)])
    records = BrewFormulaReader(http).read([jetty])
    assert records == [
        DependencyRecord(
            "jetty", "gz-physics", 9, "bullet", "brew", label, "bullet", "3.25", "homebrew-core"
        )
        for label in TWO_BOTTLES
    ] + [
        DependencyRecord(
            "jetty", "gz-physics", 9, "dart", "brew", label, "dartsim", "6.19.4", "homebrew-core"
        )
        for label in TWO_BOTTLES
    ]
    # The tap was asked first, and has no `dartsim`.
    assert http.requested.index(tap("dartsim")) < http.requested.index(core("dartsim"))


def test_a_name_neither_the_tap_nor_core_carries_resolves_to_nothing(http):
    # As if the tap dropped ogre2.3: homebrew-core has no ogre-next to fall back on.
    del http.bodies[tap("ogre2.3")]
    reader = BrewFormulaReader(http)
    records = reader.read([Collection("jetty", False, [Library("gz-rendering", 10)])])
    ogre_next = [r for r in records if r.dependency == "ogre-next"]
    assert [(r.declared, r.version, r.origin) for r in ogre_next] == [("ogre2.3", None, "")] * 3
    assert core("ogre2.3") in http.requested
    assert reader.errors == []


def test_a_tap_formula_that_states_no_version_is_not_looked_up_in_core(http):
    # Synthetic: a head-only ogre2.3. The tap's formula is what gets installed,
    # so core's version of the name would be the wrong answer.
    http.add(
        tap("ogre2.3"),
        'class Ogre23 < Formula\n  head "https://github.com/OGRECave/ogre-next.git"\nend\n',
    )
    records = BrewFormulaReader(http).read(
        [Collection("jetty", False, [Library("gz-rendering", 10)])]
    )
    ogre_next = {(r.version, r.origin) for r in records if r.dependency == "ogre-next"}
    assert ogre_next == {(None, "tap")}
    assert core("ogre2.3") not in http.requested


def test_build_and_test_only_tracked_dependencies_get_no_record(http):
    # Synthetic, hand-written from gz-physics9: every tracked name but the last
    # two is build- or test-only, and uses_from_macos is not a dependency.
    http.add(
        tap("gz-physics9"),
        'class GzPhysics9 < Formula\n'
        '  url "https://osrf-distributions.s3.amazonaws.com/gz-physics/releases/gz-physics-9.5.1.tar.bz2"\n'
        '  depends_on "dartsim" => :build\n'
        '  depends_on "ogre1.9" => :test\n'
        '  depends_on "ogre2.3" => [:build, :test]\n'
        '  uses_from_macos "bullet"\n'
        '  depends_on "dartsim@6.10.0"\n'
        '  depends_on "bullet@2.87"\n'
        'end\n',
    )
    records = BrewFormulaReader(http).read([Collection("jetty", False, [Library("gz-physics", 9)])])
    assert records == [
        DependencyRecord(
            "jetty", "gz-physics", 9, "dart", "brew", "source-only", "dartsim@6.10.0", "6.10.0", "tap"
        ),
        DependencyRecord(
            "jetty", "gz-physics", 9, "bullet", "brew", "source-only", "bullet@2.87", "2.87", "tap"
        ),
    ]
    for skipped in ("dartsim", "ogre1.9", "ogre2.3", "bullet"):
        assert tap(skipped) not in http.requested


def test_a_formula_with_no_bottles_gets_source_only_records(http):
    # gz-rotary-physics is head-only and bottles nothing.
    rotary = Collection("rotary", False, [Library("gz-rotary-physics", 1)])
    records = BrewFormulaReader(http).read([rotary])
    assert records == [
        DependencyRecord(
            "rotary", "gz-rotary-physics", 1, "bullet", "brew", "source-only", "bullet", "3.25",
            "homebrew-core",
        ),
        DependencyRecord(
            "rotary", "gz-rotary-physics", 1, "dart", "brew", "source-only", "dartsim", "6.19.4",
            "homebrew-core",
        ),
    ]


def test_an_unmapped_formula_the_tap_hosts_is_reported(http):
    # sdformat9 declares tinyxml1, which the tap hosts and no alias names. Its
    # doxygen and urdfdom are not in the tap, so they are nobody's to track.
    # The tinyxml1 and ignition-math6 bodies are stand-ins: only their
    # existence is read. ignition-* is a gz formula, never reported.
    http.add(tap("tinyxml1"), "class Tinyxml1 < Formula\nend\n")
    http.add(tap("ignition-math6"), "class IgnitionMath6 < Formula\nend\n")
    http.add(tap("ignition-tools"), fixture_text("brew-ignition-tools.rb"))
    reader = BrewFormulaReader(http)
    records = reader.read([Collection("citadel", False, [Library("sdformat", 9)])])
    assert records == []
    assert reader.errors == [
        FetchError("deps:aliases", "citadel/sdformat9 declares tinyxml1 (osrf/simulation tap) with no alias")
    ]


def test_errors_are_those_of_the_last_read(http):
    http.add(tap("tinyxml1"), "class Tinyxml1 < Formula\nend\n")
    reader = BrewFormulaReader(http)
    citadel = Collection("citadel", False, [Library("sdformat", 9)])
    reader.read([citadel])
    reader.read([citadel])
    assert len(reader.errors) == 1


def test_a_collection_homebrew_does_not_publish_is_not_read(http, monkeypatch):
    # Synthetic exclusion: homebrew publishes every collection today.
    monkeypatch.setitem(
        config.COLLECTION_SOURCES_EXCLUDED, "harmonic", frozenset({"bazel_registry", "homebrew"})
    )
    harmonic = Collection("harmonic", False, [Library("gz-physics", 9)])
    jetty = Collection("jetty", False, [Library("gz-physics", 9)])
    records = BrewFormulaReader(http).read([harmonic, jetty])
    assert {r.collection for r in records} == {"jetty"}


def test_a_library_shared_by_collections_gets_records_in_each(http):
    # Synthetic sharing: gz-physics 9 is jetty's alone, but gz-tools 2 is shared
    # the same way and declares nothing tracked.
    shared = [
        Collection("ionic", False, [Library("gz-physics", 9)]),
        Collection("jetty", False, [Library("gz-physics", 9)]),
    ]
    records = BrewFormulaReader(http).read(shared)
    # bullet and dartsim, on two bottles each.
    assert Counter(r.collection for r in records) == {"ionic": 4, "jetty": 4}
