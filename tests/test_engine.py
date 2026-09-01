import pytest

from gz_release_dashboard import engine, snapshot as snap
from gz_release_dashboard.models import (
    Collection,
    GroundTruthEntry,
    Library,
    PackageRecord,
    Status,
)


def record(library, major, version, *, source="osrf_debian", channel="stable",
           platform="noble", arch="amd64"):
    return PackageRecord(
        source=source, channel=channel, platform=platform, arch=arch,
        library=library, major=major, pkg_name=f"{library}{major}",
        raw_version=version, upstream_version=version,
    )


def build(collections, ground_truth, records, sources=("osrf_debian",)):
    s = snap.new_snapshot(list(sources))
    s.collections = collections
    s.ground_truth = ground_truth
    s.records = records
    return s


@pytest.fixture
def jetty():
    return Collection("jetty", False, [Library("gz-sim", 10), Library("gz-math", 9)])


@pytest.fixture
def truth():
    return [
        GroundTruthEntry("gz-sim", 10, "10.5.0", "10.6.0-pre1"),
        GroundTruthEntry("gz-math", 9, "9.3.0", None),
    ]


def statuses(snapshot):
    return {
        (e.library, e.channel, e.platform, e.arch): e.status
        for e in engine.compute_statuses(snapshot)
    }


def test_expected_version_per_channel():
    entry = GroundTruthEntry("gz-sim", 10, "10.5.0", "10.6.0-pre1")
    assert engine.expected_version(entry, "stable") == "10.5.0"
    assert engine.expected_version(entry, "prerelease") == "10.6.0-pre1"
    assert engine.expected_version(entry, "ros2-testing") == "10.6.0-pre1"


def test_a_stale_prerelease_tag_never_beats_the_stable_one():
    entry = GroundTruthEntry("gz-sim", 10, "10.5.0", "10.0.0-pre2")
    assert engine.expected_version(entry, "prerelease") == "10.5.0"


def test_a_development_major_is_measured_against_its_prerelease():
    entry = GroundTruthEntry("gz-sim", 11, None, "11.0.0-pre1")
    assert engine.expected_version(entry, "stable") == "11.0.0-pre1"


@pytest.mark.parametrize(
    "found,expected,status",
    [
        ("10.5.0", "10.5.0", Status.UP_TO_DATE),
        ("10.4.0", "10.5.0", Status.BEHIND),
        ("10.6.0", "10.5.0", Status.AHEAD),
        ("10.6.0-pre1", "10.6.0-pre1", Status.UP_TO_DATE),
        ("10.5.0", None, Status.AHEAD),
    ],
)
def test_compare_reaches_every_present_status(found, expected, status):
    assert engine.compare(found, expected) is status


def test_up_to_date_behind_and_ahead(jetty, truth):
    s = build([jetty], truth, [record("gz-sim", 10, "10.5.0"),
                               record("gz-math", 9, "9.1.0")])
    result = statuses(s)
    assert result[("gz-sim", "stable", "noble", "amd64")] is Status.UP_TO_DATE
    assert result[("gz-math", "stable", "noble", "amd64")] is Status.BEHIND


def test_a_library_absent_from_a_populated_platform_is_missing(jetty, truth):
    s = build(
        [jetty],
        truth,
        [
            record("gz-sim", 10, "10.5.0"),
            record("gz-math", 9, "9.3.0"),
            # A second platform builds only half the collection...
            record("gz-sim", 10, "10.5.0", platform="resolute"),
            # ...and gz-math is built for amd64 elsewhere, so its absence counts.
        ],
    )
    assert statuses(s)[("gz-math", "stable", "resolute", "amd64")] is Status.MISSING


def test_a_library_never_built_for_an_architecture_is_not_expected(jetty, truth):
    s = build(
        [jetty],
        truth,
        [
            record("gz-sim", 10, "10.5.0"),
            record("gz-math", 9, "9.3.0"),
            record("gz-math", 9, "9.3.0", arch="armhf"),
        ],
    )
    # gz-sim 10 exists for no armhf build anywhere, so armhf must stay quiet.
    assert statuses(s)[("gz-sim", "stable", "noble", "armhf")] is Status.NOT_EXPECTED


def test_one_leaked_package_does_not_put_a_collection_on_a_platform(truth):
    jetty = Collection(
        "jetty", False,
        [Library("gz-sim", 10), Library("gz-math", 9), Library("gz-gui", 10),
         Library("gz-msgs", 12)],
    )
    s = build(
        [jetty],
        truth,
        [
            record("gz-sim", 10, "10.5.0"),
            record("gz-math", 9, "9.3.0"),
            record("gz-gui", 10, "10.1.0"),
            record("gz-msgs", 12, "12.0.0"),
            # gz-math 9 is shared with another collection and leaked onto focal.
            record("gz-math", 9, "9.3.0", platform="focal"),
        ],
    )
    reached = {(e.platform) for e in engine.compute_statuses(s)}
    assert reached == {"noble"}


def test_an_in_development_collection_is_not_expected_on_stable_channels():
    dev = Collection("m", True, [Library("gz-sim", 11), Library("gz-math", 10)])
    s = build(
        [dev],
        [GroundTruthEntry("gz-sim", 11, None, "11.0.0-pre1")],
        [record("gz-sim", 11, "11.0.0-pre1")],
    )
    result = statuses(s)
    assert result[("gz-sim", "stable", "noble", "amd64")] is Status.UP_TO_DATE
    assert result[("gz-math", "stable", "noble", "amd64")] is Status.NOT_EXPECTED


def test_a_source_that_never_ships_a_library_is_not_expected_to(jetty, truth):
    jetty.libraries.append(Library("gz-gui", 10))
    s = build(
        [jetty],
        truth,
        [
            record("gz-sim", 10, "10.5.0", source="bazel_registry", channel="",
                   platform="all", arch="all"),
            record("gz-math", 9, "9.3.0", source="bazel_registry", channel="",
                   platform="all", arch="all"),
        ],
        sources=("bazel_registry",),
    )
    result = statuses(s)
    assert result[("gz-gui", "", "all", "all")] is Status.NOT_EXPECTED


def test_staging_channels_never_report_missing(jetty, truth):
    s = build(
        [jetty],
        truth,
        [
            record("gz-sim", 10, "10.5.0", source="ros_vendor", channel="ros2-testing",
                   platform="rolling@noble"),
            record("gz-math", 9, "9.3.0", source="ros_vendor", channel="ros2-testing",
                   platform="rolling@noble"),
            record("gz-sim", 10, "10.5.0", source="ros_vendor", channel="ros2-testing",
                   platform="rolling@resolute"),
        ],
        sources=("ros_vendor",),
    )
    result = statuses(s)
    assert result[("gz-math", "ros2-testing", "rolling@resolute", "amd64")] is (
        Status.NOT_EXPECTED
    )


def test_an_overlay_channel_is_reported_only_where_it_holds_something(jetty, truth):
    """No absence cells at all: the osrf prerelease repository sits on top of
    stable, so an empty slot means nothing is queued, not that something is
    gone. Only what the source kept -- already filtered down to versions ahead
    of stable -- gets a cell, and a pending release is exactly what belongs
    there, so it is up to date whatever the tags say.
    """
    s = build(
        [jetty],
        truth,
        [
            record("gz-sim", 10, "10.6.0-pre1", channel="prerelease"),
            record("gz-math", 9, "9.3.0"),
        ],
    )
    result = statuses(s)
    assert result[("gz-sim", "prerelease", "noble", "amd64")] is Status.UP_TO_DATE
    assert ("gz-math", "prerelease", "noble", "amd64") not in result


def test_an_overlay_channel_is_up_to_date_even_behind_its_tag(jetty, truth):
    """A newer tag existing does not make a staged release wrong: it is ahead of
    stable, which is the whole claim the prerelease column makes.
    """
    s = build([jetty], truth, [record("gz-sim", 10, "10.5.1", channel="prerelease")])
    assert statuses(s)[("gz-sim", "prerelease", "noble", "amd64")] is Status.UP_TO_DATE


def test_problems_exclude_ahead_and_staging_channels(jetty, truth):
    s = build(
        [jetty],
        truth,
        [
            record("gz-sim", 10, "10.9.0"),                        # ahead
            record("gz-math", 9, "9.1.0"),                         # behind, stable
            record("gz-sim", 10, "10.1.0", channel="prerelease"),  # behind, staging
            record("gz-math", 9, "9.1.0", channel="prerelease"),
        ],
    )
    found = engine.problems(engine.compute_statuses(s))
    assert [(e.library, e.channel, e.status) for e in found] == [
        ("gz-math", "stable", Status.BEHIND)
    ]


def test_a_matching_prerelease_counts_as_up_to_date():
    """An unreleased collection shipping exactly its latest tag is not a problem."""
    dev = Collection("m", True, [Library("gz-sim", 11)])
    s = build(
        [dev],
        [GroundTruthEntry("gz-sim", 11, None, "11.0.0-pre1")],
        [record("gz-sim", 11, "11.0.0-pre1", channel="prerelease")],
    )
    entries = engine.compute_statuses(s)
    assert [e.status for e in entries] == [Status.UP_TO_DATE]
    assert engine.problems(entries) == []


def test_a_prerelease_behind_its_own_tag_is_still_behind():
    dev = Collection("m", True, [Library("gz-sim", 11)])
    s = build(
        [dev],
        [GroundTruthEntry("gz-sim", 11, None, "11.0.0-pre3")],
        [record("gz-sim", 11, "11.0.0-pre1")],
    )
    assert engine.compute_statuses(s)[0].status is Status.BEHIND


def cells(snapshot):
    """Which (collection, channel, platform) cells were scored at all."""
    return {
        (e.collection, e.channel, e.platform)
        for e in engine.compute_statuses(snapshot)
    }


def vendor(library, major, version, rosdistro, channel="ros2", distro="noble"):
    return record(library, major, version, source="ros_vendor", channel=channel,
                  platform=f"{rosdistro}@{distro}")


@pytest.fixture
def two_generations():
    """jetty, then m: the order gz-collections.yaml lists them in."""
    return [
        Collection("jetty", False, [Library("gz-sim", 10), Library("gz-math", 9)]),
        Collection("m", True, [Library("gz-sim", 11), Library("gz-math", 10)]),
    ]


@pytest.fixture
def two_generation_truth():
    return [
        GroundTruthEntry("gz-sim", 10, "10.5.0", None),
        GroundTruthEntry("gz-math", 9, "9.3.0", None),
        GroundTruthEntry("gz-sim", 11, None, "11.0.0-pre1"),
        GroundTruthEntry("gz-math", 10, None, "10.0.0-pre1"),
    ]


def test_rolling_is_scored_against_the_newest_collection_that_carries_it(
    two_generations, two_generation_truth
):
    """Rolling keeps the old generation's packages long after it has moved on.

    Both jetty's and m's libraries are in Rolling here, exactly as they are
    upstream. Scoring jetty against it would report a lag that no jetty release
    can ever fix, because Rolling is not where jetty goes any more.
    """
    s = build(
        two_generations,
        two_generation_truth,
        [
            vendor("gz-sim", 10, "10.1.1", "rolling"),   # frozen, left behind
            vendor("gz-math", 9, "9.1.0", "rolling"),
            vendor("gz-sim", 11, "11.0.0-pre1", "rolling"),
            vendor("gz-math", 10, "10.0.0-pre1", "rolling"),
        ],
        sources=("ros_vendor",),
    )
    assert engine.rolling_collection(s) == "m"
    scored = cells(s)
    assert ("m", "ros2", "rolling@noble") in scored
    assert ("jetty", "ros2", "rolling@noble") not in scored
    assert engine.problems(engine.compute_statuses(s)) == []


def test_a_pinned_rosdistro_stays_with_its_own_collection(
    two_generations, two_generation_truth
):
    """Only Rolling moves. lyrical is jetty's ROS distribution and stays there."""
    s = build(
        two_generations,
        two_generation_truth,
        [
            vendor("gz-sim", 10, "10.5.0", "lyrical", distro="resolute"),
            vendor("gz-math", 9, "9.3.0", "lyrical", distro="resolute"),
            vendor("gz-sim", 11, "11.0.0-pre1", "rolling"),
            vendor("gz-math", 10, "10.0.0-pre1", "rolling"),
        ],
        sources=("ros_vendor",),
    )
    assert ("jetty", "ros2", "lyrical@resolute") in cells(s)


def test_a_shared_major_cannot_claim_rolling(two_generations, two_generation_truth):
    """harmonic and ionic each have one library in Rolling; that is a leak.

    The newest collection wins only among those Rolling really carries, so a
    single shared major must not hand Rolling to a collection it left years ago.
    """
    # Four libraries, so the half-share threshold is two: one shared major is
    # not enough. A two-library collection could not tell the two apart.
    two_generations.append(
        Collection("n", True, [
            Library("gz-sim", 12), Library("gz-math", 11),
            Library("gz-gui", 12), Library("gz-msgs", 14),
        ])
    )
    s = build(
        two_generations,
        two_generation_truth,
        [
            vendor("gz-sim", 11, "11.0.0-pre1", "rolling"),
            vendor("gz-math", 10, "10.0.0-pre1", "rolling"),
            vendor("gz-sim", 12, "12.0.0-pre1", "rolling"),  # one library of n
        ],
        sources=("ros_vendor",),
    )
    assert engine.rolling_collection(s) == "m"


def test_rolling_with_nothing_recognisable_belongs_to_nobody(
    two_generations, two_generation_truth
):
    s = build(two_generations, two_generation_truth, [], sources=("ros_vendor",))
    assert engine.rolling_collection(s) is None


def test_rosdistro_of_leaves_other_platforms_alone():
    assert engine.rosdistro_of("rolling@noble") == "rolling"
    assert engine.rosdistro_of("noble") == "noble"
    assert engine.rosdistro_of("linux-64") == "linux-64"
