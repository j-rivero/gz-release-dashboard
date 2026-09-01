from rich.console import Console

from gz_release_dashboard import engine, snapshot as snap
from gz_release_dashboard.models import (
    Collection,
    FetchError,
    GroundTruthEntry,
    Library,
    PackageRecord,
    Status,
    StatusEntry,
)
from gz_release_dashboard.render import aggregate_cell, column_order
from gz_release_dashboard.render import console as console_render


def entry(status, found=None, expected=None, platform="noble", arch="amd64"):
    return StatusEntry(
        collection="jetty", library="gz-sim", major=10, source="osrf_debian",
        channel="stable", platform=platform, arch=arch, status=status,
        found_version=found, expected_version=expected,
    )


def test_aggregate_cell_is_empty_without_entries():
    assert aggregate_cell([]) is None


def test_the_worst_status_wins():
    cell = aggregate_cell([
        entry(Status.UP_TO_DATE, "10.5.0"),
        entry(Status.MISSING, expected="10.5.0", arch="arm64"),
    ])
    assert cell.status is Status.MISSING
    # ...but the version the source does ship is still reported.
    assert cell.version == "10.5.0"
    assert (cell.worst_count, cell.total) == (1, 2)
    assert cell.mixed


def test_a_behind_cell_names_the_version_that_is_behind():
    cell = aggregate_cell([
        entry(Status.BEHIND, "10.4.0", "10.5.0"),
        entry(Status.BEHIND, "10.3.0", "10.5.0", arch="arm64"),
        entry(Status.UP_TO_DATE, "10.5.0", "10.5.0", arch="armhf"),
    ])
    assert (cell.status, cell.version, cell.expected) == (Status.BEHIND, "10.3.0", "10.5.0")


def test_not_expected_cells_are_left_out_of_the_ratio():
    cell = aggregate_cell([
        entry(Status.UP_TO_DATE, "10.5.0"),
        entry(Status.NOT_EXPECTED, arch="i386"),
    ])
    assert (cell.status, cell.total) == (Status.UP_TO_DATE, 1)
    assert not cell.mixed


def test_a_wholly_unexpected_cell_still_renders():
    cell = aggregate_cell([entry(Status.NOT_EXPECTED), entry(Status.NOT_EXPECTED, arch="i386")])
    assert cell.status is Status.NOT_EXPECTED


def test_column_order_expands_channels_and_ignores_unfetched_sources():
    assert column_order(["osrf_debian"]) == [
        ("osrf_debian", "stable"),
        ("osrf_debian", "prerelease"),
    ]
    assert column_order([]) == []


def build_snapshot():
    s = snap.new_snapshot(["osrf_debian"])
    s.collections = [
        Collection("jetty", False, [Library("gz-sim", 10), Library("gz-math", 9)]),
        Collection("m", True, [Library("gz-sim", 11)]),
    ]
    s.ground_truth = [
        GroundTruthEntry("gz-sim", 10, "10.5.0", None),
        GroundTruthEntry("gz-math", 9, "9.3.0", None),
        GroundTruthEntry("gz-sim", 11, None, "11.0.0-pre1"),
    ]
    s.records = [
        PackageRecord("osrf_debian", "stable", "noble", "amd64", "gz-sim", 10,
                      "gz-sim10", "10.5.0-1~noble", "10.5.0"),
        PackageRecord("osrf_debian", "stable", "noble", "amd64", "gz-math", 9,
                      "gz-math9", "9.1.0-1~noble", "9.1.0"),
        # The in-development collection only ever reaches the staging channel.
        PackageRecord("osrf_debian", "prerelease", "noble", "amd64", "gz-sim", 11,
                      "gz-sim11", "11.0.0~pre1-1~noble", "11.0.0-pre1"),
    ]
    s.errors = [FetchError("conda_forge", "connection reset")]
    return s


def render(**kwargs):
    snapshot = build_snapshot()
    entries = engine.compute_statuses(snapshot)
    console = Console(record=True, width=200, force_terminal=False)
    count = console_render.render(snapshot, entries, console, **kwargs)
    return count, console.export_text()


def test_render_shows_a_table_per_collection_with_glyphs():
    count, text = render()
    assert "jetty" in text and "m  [in development]" in text
    assert "gz-sim (10)" in text and "✅ 10.5.0" in text
    assert "🔶 9.1.0" in text and "→ 9.3.0" in text
    assert "🚧 11.0.0-pre1" in text


def test_render_lists_the_problems_and_counts_them():
    count, text = render()
    assert count == 1
    assert "problems (1)" in text
    assert "jetty/gz-math9 9.1.0 < 9.3.0 in osrf deb stable — noble/amd64" in text


def test_render_surfaces_fetch_errors():
    _, text = render()
    assert "fetch errors (1)" in text
    assert "conda_forge: connection reset" in text


def test_problems_only_hides_the_tables():
    _, text = render(problems_only=True)
    assert "problems (1)" in text
    assert "gz-sim (10)" not in text


def test_verbose_adds_the_per_platform_details():
    _, text = render(verbose=True)
    assert "details" in text
    assert "not expected" in text


def test_a_clean_snapshot_reports_no_problems():
    snapshot = build_snapshot()
    snapshot.records[1].upstream_version = "9.3.0"
    snapshot.errors = []
    console = Console(record=True, width=200)
    count = console_render.render(snapshot, engine.compute_statuses(snapshot), console)
    assert count == 0
    assert "every source matches the latest release" in console.export_text()


def test_problems_that_differ_only_by_platform_collapse_into_one_line():
    snapshot = build_snapshot()
    snapshot.records = [
        r for r in snapshot.records if (r.library, r.channel) != ("gz-math", "stable")
    ]
    for arch in ("amd64", "arm64", "armhf"):
        snapshot.records.append(
            PackageRecord("osrf_debian", "stable", "noble", arch, "gz-sim", 10,
                          "gz-sim10", "10.5.0-1~noble", "10.5.0"))
        snapshot.records.append(
            PackageRecord("osrf_debian", "stable", "noble", arch, "gz-math", 9,
                          "gz-math9", "9.1.0-1~noble", "9.1.0"))
    entries = engine.compute_statuses(snapshot)
    console = Console(record=True, width=200)
    count = console_render.render(snapshot, entries, console)
    text = console.export_text()
    # One finding, three platform cells.
    assert count == 3
    assert "problems (1, 3 platform cells)" in text
    assert "noble/amd64, noble/arm64, noble/armhf" in text
