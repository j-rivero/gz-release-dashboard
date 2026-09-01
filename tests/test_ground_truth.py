import subprocess

import pytest
from conftest import fixture_text

from gz_release_dashboard import ground_truth as gt
from gz_release_dashboard.models import Collection, Library


@pytest.fixture
def tags():
    return gt.parse_ls_remote(fixture_text("ls-remote-gz-sim.txt"))


def test_parse_ls_remote_drops_peeled_refs_and_branches(tags):
    assert "gz-sim10_10.5.0" in tags
    assert not any(t.endswith("^{}") for t in tags)
    assert not any("refs/heads" in t for t in tags)


def test_candidate_prefixes_cover_the_ignition_era():
    assert gt.candidate_tag_prefixes("gz-sim", 6) == (
        "gz-sim6_",
        "ignition-gazebo6_",
        "ign-gazebo6_",
        "gz-sim_",
        "ignition-gazebo_",
        "ign-gazebo_",
    )


def test_sdformat_keeps_its_own_prefix():
    assert gt.candidate_tag_prefixes("sdformat", 16) == ("sdformat16_", "sdformat_")


def test_the_first_ignition_major_used_an_unsuffixed_prefix(tags):
    # gz-tools 1 and gz-plugin 1 only ever had `ignition-tools_1.5.0` tags.
    entry = gt.entry_for(tags, Library("gz-tools", 1))
    assert entry.latest_stable == "1.5.0"


def test_an_unsuffixed_prefix_never_leaks_a_foreign_major(tags):
    assert gt.versions_for(tags, "gz-tools", 2) == []


def test_latest_stable_and_prerelease_per_major(tags):
    jetty = gt.entry_for(tags, Library("gz-sim", 10))
    assert jetty.latest_stable == "10.5.0"
    assert jetty.latest_prerelease == "10.6.0-pre1"


def test_ignition_era_tags_resolve(tags):
    fortress = gt.entry_for(tags, Library("gz-sim", 6))
    assert fortress.latest_stable == "6.18.0"
    assert fortress.latest_prerelease == "6.19.0-pre1"


def test_development_major_has_no_stable_release(tags):
    dev = gt.entry_for(tags, Library("gz-sim", 11))
    assert dev.latest_stable is None
    assert dev.latest_prerelease == "11.0.0-pre2"


def test_junk_tags_are_rejected(tags):
    # gz-sim10_10.0.0-bcr-test, migrated_from_bitbucket and the pre-2020
    # `_pre1` spelling must never be mistaken for a release.
    versions = [str(v) for v in gt.versions_for(tags, "gz-sim", 10)]
    assert versions == ["10.4.0", "10.5.0", "10.6.0-pre1"]
    assert gt.versions_for(tags, "gz-sim", 2) == []


def test_a_major_with_no_tags_at_all(tags):
    entry = gt.entry_for(tags, Library("gz-gui", 10))
    assert entry.latest_stable is None and entry.latest_prerelease is None


def test_build_ground_truth_queries_each_repo_once(monkeypatch):
    calls = []

    def fake(url):
        calls.append(url)
        return fixture_text("ls-remote-gz-sim.txt")

    monkeypatch.setattr(gt, "run_ls_remote", fake)
    collections = [
        Collection("jetty", False, [Library("gz-sim", 10), Library("gz-math", 9)]),
        Collection("fortress", False, [Library("gz-sim", 6)]),
    ]
    entries, errors = gt.build_ground_truth(collections)
    assert errors == []
    assert sorted(calls) == [
        "https://github.com/gazebosim/gz-math.git",
        "https://github.com/gazebosim/gz-sim.git",
    ]
    assert {(e.library, e.major, e.latest_stable) for e in entries} == {
        ("gz-sim", 10, "10.5.0"),
        ("gz-sim", 6, "6.18.0"),
        ("gz-math", 9, None),
    }


def test_a_failing_repo_is_a_non_fatal_error(monkeypatch):
    def boom(url):
        raise subprocess.CalledProcessError(128, url)

    monkeypatch.setattr(gt, "run_ls_remote", boom)
    entries, errors = gt.build_ground_truth(
        [Collection("jetty", False, [Library("gz-sim", 10)])]
    )
    assert [e.source for e in errors] == ["ground_truth"]
    assert entries[0].latest_stable is None
