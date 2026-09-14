from gz_release_dashboard.deps.inventory import dependency_rows, narrow_rows
from gz_release_dashboard.models import DependencyRecord


def rec(
    system,
    version,
    platform="all",
    *,
    dependency="dart",
    collection="jetty",
    library="gz-physics",
    major=9,
    declared="declared",
    origin="origin",
    label=None,
    channel="",
):
    return DependencyRecord(
        collection=collection,
        library=library,
        major=major,
        dependency=dependency,
        system=system,
        platform=platform,
        declared=declared,
        version=version,
        origin=origin,
        label=label,
        channel=channel,
    )


def row_for(records, dependency="dart", collection="jetty"):
    [row] = [
        r
        for r in dependency_rows(records)
        if r.dependency == dependency and r.collection == collection
    ]
    return row


def test_platforms_of_one_system_that_disagree_warn():
    # osrf's libogre-next-2.3-dev as it stands: noble never got 2.3.3.
    row = row_for(
        [
            rec("deb", "2.3.1", "noble/amd64", dependency="ogre-next"),
            rec("deb", "2.3.1", "noble/arm64", dependency="ogre-next"),
            rec("deb", "2.3.3", "resolute/amd64", dependency="ogre-next"),
            rec("deb", "2.3.3", "resolute/arm64", dependency="ogre-next"),
        ],
        dependency="ogre-next",
    )
    cell = row.cells["deb"]
    assert cell.warn
    assert cell.text == "2.3.1–2.3.3"
    assert cell.lowest_platforms == ["noble/amd64", "noble/arm64"]
    assert not row.diverges


def test_a_range_is_ordered_numerically():
    row = row_for([rec("deb", "6.16.6", "noble/amd64"), rec("deb", "6.9.0", "jammy/amd64")])
    assert row.cells["deb"].text == "6.9.0–6.16.6"


def test_agreeing_platforms_neither_warn_nor_show_a_range():
    row = row_for([rec("deb", "6.16.6", "noble/amd64"), rec("deb", "6.16.6", "resolute/arm64")])
    assert not row.cells["deb"].warn
    assert row.cells["deb"].text == "6.16.6"


def test_the_same_version_spelled_with_a_trailing_zero_agrees():
    row = row_for(
        [
            rec("brew", "1.9", "arm64_sonoma", dependency="ogre"),
            rec("brew", "1.9.0", "sonoma", dependency="ogre"),
        ],
        dependency="ogre",
    )
    assert not row.cells["brew"].warn


def test_systems_on_different_series_diverge():
    # jetty's dart today: three series across five systems, each self-consistent.
    row = row_for(
        [
            rec("deb", "6.16.6", "noble/amd64"),
            rec("deb", "6.16.6", "resolute/amd64"),
            rec("ros", "6.16.6", "lyrical@resolute/amd64"),
            rec("conda", "6.19.4", "linux-64"),
            rec("brew", "6.19.4", "arm64_sonoma"),
            rec("bazel", "6.13.2"),
        ]
    )
    assert row.diverges
    assert not any(cell.warn for cell in row.cells.values())
    assert row.cells["conda"].text == "6.19.4"


def test_a_patch_difference_between_systems_is_not_marked():
    row = row_for(
        [
            rec("deb", "2.3.3", "resolute/amd64", dependency="ogre-next"),
            rec("bazel", "2.3.1", dependency="ogre-next"),
        ],
        dependency="ogre-next",
    )
    assert not row.diverges


def test_a_system_holding_an_extra_series_diverges_from_one_that_does_not():
    row = row_for(
        [
            rec("deb", "6.13.2", "jammy/amd64"),
            rec("deb", "6.16.6", "noble/amd64"),
            rec("ros", "6.16.6", "lyrical@resolute/amd64"),
        ]
    )
    assert row.cells["deb"].warn
    assert row.diverges


def test_a_vendor_without_a_version_shows_its_label_and_is_not_compared():
    row = row_for(
        [
            rec("deb", "1.5.0", "noble/amd64", dependency="zenoh"),
            rec("ros", None, "lyrical@resolute/amd64", dependency="zenoh",
                label="vendor 0.10.5"),
        ],
        dependency="zenoh",
    )
    assert row.cells["ros"].text == "vendor 0.10.5"
    assert not row.cells["ros"].warn
    assert not row.diverges


def test_an_unresolved_declaration_is_a_question_mark_that_compares_with_nothing():
    row = row_for([rec("deb", None, "noble/arm64"), rec("deb", "6.16.6", "noble/amd64")])
    assert row.cells["deb"].text == "6.16.6"
    assert not row.cells["deb"].warn
    alone = row_for([rec("brew", None, "sonoma")])
    assert alone.cells["brew"].text == "?"


def test_rows_are_kept_apart_per_collection():
    records = [
        rec("deb", "6.13.2", "jammy/amd64", collection="harmonic"),
        rec("conda", "6.19.4", "linux-64", collection="jetty"),
    ]
    assert not row_for(records, collection="harmonic").diverges
    assert not row_for(records, collection="jetty").diverges
    assert set(row_for(records, collection="jetty").cells) == {"conda"}


def test_rows_are_sorted_by_collection_then_dependency():
    records = [
        rec("deb", "1.5.0", dependency="zenoh", collection="jetty"),
        rec("deb", "6.16.6", dependency="dart", collection="jetty"),
        rec("deb", "6.13.2", dependency="dart", collection="harmonic"),
    ]
    assert [(r.collection, r.dependency) for r in dependency_rows(records)] == [
        ("harmonic", "dart"),
        ("jetty", "dart"),
        ("jetty", "zenoh"),
    ]


def test_a_narrowed_view_keeps_the_marks_of_the_whole():
    """`--source` and `--lib` choose what is shown; they must not move a mark.

    Cut down to its deb cell, dart would have nothing to diverge from, and cut
    down to one declaring library the deb cell would agree with itself.
    """
    rows = dependency_rows(
        [
            rec("deb", "6.13.2", "jammy/amd64"),
            rec("deb", "6.16.6", "noble/amd64", library="gz-sim", major=10),
            rec("conda", "6.19.4", "linux-64"),
        ]
    )
    [row] = narrow_rows(rows, lambda r: r.system == "deb" and r.library == "gz-physics")
    assert set(row.cells) == {"deb"}
    assert row.cells["deb"].text == "6.13.2"
    assert row.cells["deb"].warn
    assert row.diverges


def test_narrowing_drops_the_cells_and_rows_it_empties():
    rows = dependency_rows([rec("deb", "6.16.6"), rec("conda", "1.5.0", dependency="zenoh")])
    narrowed = narrow_rows(rows, lambda r: r.system == "conda")
    assert [(r.dependency, list(r.cells)) for r in narrowed] == [("zenoh", ["conda"])]


def test_a_staging_channel_sits_beside_the_cells_and_is_never_marked():
    """osrf prerelease holds zenoh 1.8.0 while stable has 1.5.0, as of 2026-09-14.

    What is queued is not what anyone installs: it takes no part in ◇, and a
    staging cell that disagrees with itself does not warn.
    """
    row = row_for(
        [
            rec("deb", "1.5.0", "noble/amd64", dependency="zenoh", channel="stable"),
            rec("deb", "1.8.0", "noble/amd64", dependency="zenoh", channel="prerelease"),
            rec("deb", "1.7.0", "resolute/amd64", dependency="zenoh", channel="prerelease"),
            rec("conda", "1.5.0", "linux-64", dependency="zenoh"),
        ],
        dependency="zenoh",
    )
    assert set(row.cells) == {"deb", "conda"}
    assert row.cells["deb"].text == "1.5.0"
    assert row.staged["deb"].text == "1.7.0–1.8.0"
    assert not row.staged["deb"].warn
    assert not row.diverges
    assert row.cell("deb", "prerelease") is row.staged["deb"]
    assert row.cell("deb", "stable") is row.cells["deb"]
    assert row.cell("conda") is row.cells["conda"]


def test_narrowing_keeps_what_is_staged_and_the_marks_of_the_whole():
    rows = dependency_rows(
        [
            rec("deb", "1.5.0", dependency="zenoh", channel="stable"),
            rec("deb", "1.8.0", dependency="zenoh", channel="prerelease"),
            rec("conda", "1.9.0", dependency="zenoh"),
        ]
    )
    [deb_only] = narrow_rows(rows, lambda r: r.system == "deb")
    assert deb_only.staged["deb"].text == "1.8.0"
    assert deb_only.diverges
    [queued_only] = narrow_rows(rows, lambda r: r.channel == "prerelease")
    assert queued_only.cells == {}
    assert queued_only.staged["deb"].text == "1.8.0"
