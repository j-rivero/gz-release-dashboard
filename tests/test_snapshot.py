import json

import pytest

from gz_release_dashboard import snapshot as snap
from gz_release_dashboard.models import (
    Collection,
    FetchError,
    GroundTruthEntry,
    Library,
    PackageRecord,
)


def _populated():
    s = snap.new_snapshot(["osrf_debian"])
    s.collections = [
        Collection("jetty", False, [Library("gz-sim", 10), Library("sdformat", 16)]),
        Collection("m", True, [Library("gz-sim", 11)]),
    ]
    s.ground_truth = [GroundTruthEntry("gz-sim", 10, "10.5.0", "10.0.0-pre1")]
    s.records = [
        PackageRecord(
            source="osrf_debian",
            channel="stable",
            platform="noble",
            arch="amd64",
            library="gz-sim",
            major=10,
            pkg_name="libgz-sim10-dev",
            raw_version="10.5.0-1~noble",
            upstream_version="10.5.0",
        )
    ]
    s.errors = [FetchError("conda_forge", "boom")]
    return s


def test_roundtrip_preserves_every_field(tmp_path):
    original = _populated()
    path = snap.save(original, tmp_path / "snapshot.json")
    loaded = snap.load(path)
    assert loaded == original


def test_saved_file_is_plain_json(tmp_path):
    path = snap.save(_populated(), tmp_path / "nested" / "snapshot.json")
    data = json.loads(path.read_text())
    assert data["schema_version"] == snap.SCHEMA_VERSION
    assert data["collections"][0]["libraries"][0] == {"name": "gz-sim", "major": 10}
    assert data["generated_at"].endswith("+00:00")


def test_load_rejects_a_foreign_schema(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"schema_version": 99, "generated_at": "x"}))
    with pytest.raises(ValueError, match="schema_version"):
        snap.load(path)


def test_new_snapshot_records_which_sources_ran():
    s = snap.new_snapshot(["conda_forge", "homebrew"])
    assert s.sources_fetched == ["conda_forge", "homebrew"]
    assert s.records == [] and s.errors == []
