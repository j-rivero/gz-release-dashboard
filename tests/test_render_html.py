import json

import pytest
from test_render_console import build_snapshot

from gz_release_dashboard import engine
from gz_release_dashboard.models import PackageRecord
from gz_release_dashboard.render import html as html_render


def rendered(snapshot=None):
    snapshot = snapshot or build_snapshot()
    return snapshot, html_render.render(snapshot, engine.compute_statuses(snapshot))


@pytest.fixture
def page():
    return rendered()[1]


def test_the_page_is_self_contained(page):
    assert page.startswith("<!DOCTYPE html>")
    assert "<script" not in page
    assert "<style>" in page
    # Nothing is loaded from anywhere; every asset is inline.
    assert 'src="' not in page
    assert '<link' not in page


def test_the_page_adapts_to_a_dark_colour_scheme(page):
    assert "prefers-color-scheme: dark" in page
    assert "color-scheme: light dark" in page


def test_every_collection_gets_an_anchored_section(page):
    assert '<section id="jetty">' in page
    assert '<section id="m">' in page
    assert 'href="#jetty"' in page


def test_an_in_development_collection_is_labelled(page):
    assert "in development" in page


def test_the_legend_lists_every_status(page):
    for label in ("up to date", "behind", "missing", "ahead", "prerelease", "not expected"):
        assert label in page


def test_versions_and_expectations_are_shown(page):
    assert "10.5.0" in page
    assert "&rarr; 9.3.0" in page


def test_problems_are_grouped_and_linked(page):
    assert '<section id="problems">' in page
    assert "jetty/gz-math9" in page


def test_fetch_errors_are_surfaced(page):
    assert "fetch errors" in page
    assert "connection reset" in page


def test_a_clean_run_hides_the_error_section():
    snapshot = build_snapshot()
    snapshot.errors = []
    _, page = rendered(snapshot)
    assert "fetch errors" not in page


def test_a_multi_platform_cell_becomes_a_details_disclosure():
    snapshot = build_snapshot()
    for arch in ("arm64", "armhf"):
        snapshot.records.append(
            PackageRecord("osrf_debian", "stable", "noble", arch, "gz-sim", 10,
                          "gz-sim10", "10.5.0-1~noble", "10.5.0"))
        snapshot.records.append(
            PackageRecord("osrf_debian", "stable", "noble", arch, "gz-math", 9,
                          "gz-math9", "9.1.0-1~noble", "9.1.0"))
    _, page = rendered(snapshot)
    assert "<details>" in page
    assert "noble/arm64" in page and "noble/armhf" in page


def test_a_single_platform_cell_stays_flat(page):
    # The fixture snapshot has one arch, so nothing is worth expanding.
    assert "<details>" not in page


def test_html_is_escaped():
    snapshot = build_snapshot()
    snapshot.errors[0].message = "<script>alert(1)</script>"
    _, page = rendered(snapshot)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_write_emits_the_page_and_its_snapshot(tmp_path):
    snapshot = build_snapshot()
    index = html_render.write(snapshot, engine.compute_statuses(snapshot), tmp_path / "public")
    assert index.name == "index.html"
    data = json.loads((index.parent / "snapshot.json").read_text())
    assert data["schema_version"] == snapshot.schema_version
    assert 'href="snapshot.json"' in index.read_text()


def test_the_view_counts_findings_and_the_cells_they_affect():
    snapshot = build_snapshot()
    view = html_render.build_view(snapshot, engine.compute_statuses(snapshot))
    assert len(view["problems"]) == 1
    assert view["problem_cells"] == 1
    assert view["columns"] == [
        {"source": "osrf deb", "channel": "stable"},
        {"source": "osrf deb", "channel": "prerelease"},
    ]


def test_channel_less_sources_get_an_explicit_channel_label():
    snapshot = build_snapshot()
    snapshot.sources_fetched = ["osrf_debian", "bazel_registry", "ros_vendor"]
    view = html_render.build_view(snapshot, engine.compute_statuses(snapshot))
    assert view["columns"] == [
        {"source": "osrf deb", "channel": "stable"},
        {"source": "osrf deb", "channel": "prerelease"},
        {"source": "bazel", "channel": "(all)"},
        {"source": "ros", "channel": "ros2"},
        {"source": "ros", "channel": "ros2-testing"},
    ]
