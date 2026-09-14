import pytest

from gz_release_dashboard.versions import (
    GzVersion,
    dependency_version,
    max_version,
    normalize_bcr,
    normalize_deb,
    normalize_plain,
    series,
    version_key,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("9.6.0", GzVersion(9, 6, 0)),
        ("10.1.1", GzVersion(10, 1, 1)),
        ("9.0.0-pre1", GzVersion(9, 0, 0, 1)),
        ("  9.0.0-pre12  ", GzVersion(9, 0, 0, 12)),
    ],
)
def test_parse_accepts_canonical_versions(text, expected):
    assert GzVersion.parse(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", None, "9.6", "9.6.0.1", "4.0.0-bcr-test", "migrated_from_bitbucket", "v9.6.0"],
)
def test_parse_rejects_junk(text):
    assert GzVersion.parse(text) is None


def test_stable_outranks_its_own_prereleases():
    assert GzVersion.parse("9.0.0") > GzVersion.parse("9.0.0-pre2")
    assert GzVersion.parse("9.0.0-pre2") > GzVersion.parse("9.0.0-pre1")
    assert GzVersion.parse("9.0.0-pre1") > GzVersion.parse("8.9.9")


def test_ordering_is_numeric_not_lexicographic():
    assert GzVersion.parse("10.0.0") > GzVersion.parse("9.9.9")
    assert GzVersion.parse("9.10.0") > GzVersion.parse("9.9.0")


def test_str_roundtrips():
    assert str(GzVersion.parse("9.0.0-pre1")) == "9.0.0-pre1"
    assert str(GzVersion.parse("9.6.0")) == "9.6.0"


def test_max_version_skips_unparseable():
    assert max_version(["9.5.0", "junk", None, "9.6.0", "9.6.0-pre3"]) == "9.6.0"
    assert max_version(["junk", None]) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9.6.0-1~noble", "9.6.0"),
        ("9.0.0~pre1-1~noble", "9.0.0-pre1"),
        ("10.1.1-1.995~noble", "10.1.1"),
        ("1:9.6.0-1~jammy", "9.6.0"),
        ("9.6.0", "9.6.0"),
        ("0.1.0~pre2", "0.1.0-pre2"),
        ("not-a-version", None),
    ],
)
def test_normalize_deb(raw, expected):
    assert normalize_deb(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9.6.0.bcr.1", "9.6.0"),
        ("9.6.0", "9.6.0"),
        ("9.0.0-pre1", "9.0.0-pre1"),
        ("9.0.0-pre1.bcr.2", "9.0.0-pre1"),
    ],
)
def test_normalize_bcr(raw, expected):
    assert normalize_bcr(raw) == expected


def test_normalize_plain():
    assert normalize_plain("9.6.0") == "9.6.0"
    assert normalize_plain("9.6.0_2") is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("6.16.6+ds-1~osrf1~noble", "6.16.6"),
        ("2.3.3+osrf1-4osrf~resolute", "2.3.3"),
        ("6.13.2+ds-3fakesync1build7", "6.13.2"),
        ("3.24+dfsg-2.1build1", "3.24"),
        ("2.2.6+20211021~312bf40", "2.2.6"),
        ("1.9-20160714-108ab0bcc69603dba32c0ffd4bbbc39051f421c9", "1.9"),
        ("6.10.0~20211005~d2b6ee08a60d0dbf71b0f008cd8fed1f611f6e24", "6.10.0"),
        ("3.26.0-rc0.bcr.1", "3.26.0"),
        ("6.13.2.bcr.3", "6.13.2"),
        ("v2.3.1", "2.3.1"),
        ("1:9.6.0-1~jammy", "9.6.0"),
        ("30", "30"),
        ("vendor", None),
        ("", None),
        (None, None),
    ],
)
def test_dependency_version_keeps_the_leading_dotted_number(raw, expected):
    assert dependency_version(raw) == expected


def test_dependency_versions_compare_numerically_ignoring_trailing_zeros():
    assert version_key("1.9") == version_key("1.9.0")
    assert version_key("1.10.12.1") > version_key("1.9.0")
    assert version_key("2.3.1") < version_key("2.3.3")
    assert version_key("6.9.0") < version_key("6.16.6")


def test_series_is_major_and_minor_padded_with_zeros():
    assert series("6.16.6") == (6, 16)
    assert series("1.9") == (1, 9)
    assert series("2.0.0") == series("2.0.5") == (2, 0)
    assert series("30") == (30, 0)
