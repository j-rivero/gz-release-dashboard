import pytest
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import deps
from gz_release_dashboard.deps.ros_vendor_deps import RosVendorDepsReader, upstream_version
from gz_release_dashboard.models import Collection, FetchError, Library

# The dep-ros-* indexes are the live ros2 ones of 2026-09-14, trimmed to the
# stanzas below and to Package, Version, Architecture, Depends and Description;
# every Depends line is verbatim. The madison fixtures answer exactly the
# queries these URLs spell.
ROS2 = "http://packages.ros.org/ros2/ubuntu/dists"
ROS2_TESTING = "http://packages.ros.org/ros2-testing/ubuntu/dists"
MADISON = "https://people.canonical.com/~ubuntu-archive/madison.cgi"


def index(distro, arch="amd64"):
    return f"{ROS2}/{distro}/main/binary-{arch}/Packages.gz"


def staged_index(distro, arch="amd64"):
    return f"{ROS2_TESTING}/{distro}/main/binary-{arch}/Packages.gz"


def madison(distro):
    return (
        f"{MADISON}?package=libbullet-dev+libogre-1.9-dev"
        f"&s={distro},{distro}-updates,{distro}-security&a=amd64&text=on"
    )


def jetty(distro):
    return Collection(
        "jetty", False,
        [Library("gz-physics", 9), Library("gz-rendering", 10), Library("gz-transport", 15)],
        [distro],
    )


def m():
    return Collection(
        "m", True,
        [Library("gz-physics", 10), Library("gz-rendering", 11), Library("gz-transport", 16)],
        ["resolute"],
    )


def lyrical_http():
    return (
        FakeHttpClient()
        .add_gzip(index("resolute"), fixture_text("dep-ros-resolute-amd64.txt"))
        .add(madison("resolute"), fixture_text("dep-ros-madison-resolute.txt"))
    )


def rows(records):
    return sorted(
        (
            (r.collection, r.library, r.major, r.dependency, r.platform,
             r.declared, r.version, r.origin, r.label)
            for r in records
        ),
        key=str,
    )


def test_a_gz_vendor_declares_dependency_vendors_and_plain_debian_names():
    """lyrical's gz-physics vendor depends on gz-dartsim-vendor and libbullet-dev.

    The runtime names beside them, `libbullet3.24t64 (>= 3.24+dfsg)` and
    `libogre-1.9.0t64`, match no alias and yield nothing.
    """
    reader = RosVendorDepsReader(lyrical_http())
    records = reader.read([jetty("resolute")])
    platform = "lyrical@resolute/amd64"
    assert rows(records) == sorted(
        [
            ("jetty", "gz-physics", 9, "dart", platform,
             "gz-dartsim-vendor", "6.16.6", "ros2", None),
            ("jetty", "gz-physics", 9, "bullet", platform,
             "libbullet-dev", "3.24", "ubuntu", None),
            ("jetty", "gz-rendering", 10, "ogre-next", platform,
             "gz-ogre-next-vendor", "2.3.3", "ros2", None),
            ("jetty", "gz-rendering", 10, "ogre", platform,
             "libogre-1.9-dev", "1.9.0", "ubuntu", None),
            ("jetty", "gz-transport", 15, "zenoh", platform,
             "zenoh-cpp-vendor", None, "ros2", "vendor 0.10.5"),
        ],
        key=str,
    )
    assert {r.system for r in records} == {"ros"}
    assert reader.errors == []


def test_a_vendor_whose_description_states_no_version_is_labelled_with_its_own():
    """`Vendor pkg to install zenoh-cpp`: found, but with nothing upstream to show."""
    records = RosVendorDepsReader(lyrical_http()).read([jetty("resolute")])
    assert [(r.version, r.label, r.origin) for r in records if r.dependency == "zenoh"] == [
        (None, "vendor 0.10.5", "ros2")
    ]


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Vendor package for the DART physics engine v6.16.6", "6.16.6"),
        ("Vendor package for Ogre-next v2.3.3", "2.3.3"),
        ("Vendor package for MuJoCo simulator of version 3.4.0", "3.4.0"),
        ("Vendor pkg to install zenoh-cpp", None),
    ],
)
def test_a_dependency_vendor_states_its_upstream_version_in_prose(description, expected):
    assert upstream_version(description) == expected


def test_only_the_transport_vendors_that_use_zenoh_declare_it():
    """jazzy carries a zenoh-cpp-vendor, but its gz-transport vendor does not use it.

    harmonic is cut down to its one library that matters here.
    """
    http = (
        FakeHttpClient()
        .add_gzip(index("noble"), fixture_text("dep-ros-noble-amd64.txt"))
        .add(madison("noble"), fixture_text("dep-ros-madison-noble.txt"))
    )
    harmonic = Collection("harmonic", False, [Library("gz-transport", 13)], ["noble"])
    records = RosVendorDepsReader(http).read([harmonic, jetty("noble")])
    assert [
        (r.collection, r.platform, r.label) for r in records if r.dependency == "zenoh"
    ] == [("jetty", "rolling@noble/amd64", "vendor 0.10.3")]
    assert not any(r.collection == "harmonic" for r in records)


def test_rolling_belongs_only_to_the_newest_collection_it_carries():
    """Rolling holds jetty's vendors on noble and m's on resolute at the same time.

    jetty keeps lyrical, its own distribution, and gets nothing from Rolling.
    Synthetic in one respect: m's Rolling stanzas were captured from
    ros2-testing, because the sync into ros2 had not happened yet, and are
    served here as ros2.
    """
    resolute = (
        fixture_text("dep-ros-resolute-amd64.txt")
        + "\n"
        + fixture_text("dep-ros-testing-resolute-amd64.txt")
    )
    http = (
        FakeHttpClient()
        .add_gzip(index("noble"), fixture_text("dep-ros-noble-amd64.txt"))
        .add_gzip(index("resolute"), resolute)
        .add(madison("resolute"), fixture_text("dep-ros-madison-resolute.txt"))
    )
    records = RosVendorDepsReader(http).read([jetty("noble"), m()])
    assert {(r.collection, r.platform) for r in records} == {
        ("jetty", "lyrical@resolute/amd64"),
        ("m", "rolling@resolute/amd64"),
    }
    assert [
        (r.major, r.label) for r in records if r.collection == "m" and r.dependency == "zenoh"
    ] == [(16, "vendor 0.12.0")]


def test_a_pinned_rosdistro_belongs_to_every_collection_carrying_enough_of_it():
    """Majors are shared between collections, so lyrical can serve more than one.

    Synthetic collections: `sibling` has one of its two libraries in lyrical,
    which meets the half share; `stranger` has one of four, which does not.
    """
    sibling = Collection(
        "sibling", False, [Library("gz-transport", 15), Library("gz-sim", 99)], ["resolute"]
    )
    stranger = Collection(
        "stranger", False,
        [Library("gz-transport", 15), Library("gz-sim", 98), Library("gz-gui", 98),
         Library("gz-msgs", 98)],
        ["resolute"],
    )
    records = RosVendorDepsReader(lyrical_http()).read([jetty("resolute"), sibling, stranger])
    assert {r.collection for r in records} == {"jetty", "sibling"}


def test_fortress_gets_no_ros_records_even_where_a_rosdistro_carries_it():
    # Synthetic: fortress never shipped gz-physics 9. Its name alone excludes it.
    fortress = Collection("fortress", False, [Library("gz-physics", 9)], ["resolute"])
    http = lyrical_http()
    assert RosVendorDepsReader(http).read([fortress]) == []
    assert madison("resolute") not in http.requested


class MadisonDown(FakeHttpClient):
    def get_bytes(self, url, *, ok_404=False):
        if url.startswith(MADISON):
            self.requested.append(url)
            raise ConnectionError("madison is down")
        return super().get_bytes(url, ok_404=ok_404)


def test_plain_debian_names_stay_unresolved_when_ubuntu_cannot_be_asked():
    http = MadisonDown().add_gzip(index("resolute"), fixture_text("dep-ros-resolute-amd64.txt"))
    reader = RosVendorDepsReader(http)
    records = {r.declared: r for r in reader.read([jetty("resolute")])}
    assert (records["libbullet-dev"].version, records["libbullet-dev"].origin) == (None, "")
    assert (records["libogre-1.9-dev"].version, records["libogre-1.9-dev"].origin) == (None, "")
    # The vendors come from the ROS index itself and do not need Ubuntu.
    assert (records["gz-dartsim-vendor"].version, records["gz-dartsim-vendor"].origin) == (
        "6.16.6", "ros2"
    )
    assert [e.source for e in reader.errors] == ["deps:ubuntu"]


def common_collection():
    return Collection(
        "jetty", False, [Library("gz-common", 7), Library("gz-math", 9)], ["resolute"]
    )


def test_a_vendor_ros_packages_itself_is_no_gap_in_the_alias_table():
    """Every lyrical gz-common vendor depends on spdlog-vendor, which is ROS's own.

    The alias table lists what Gazebo packages, so a ROS vendor missing from it
    says nothing about the table; reporting it would be noise on every run.
    """
    reader = RosVendorDepsReader(lyrical_http())
    assert reader.read([common_collection()]) == []
    assert reader.errors == []


def test_a_gazebo_dependency_vendor_the_alias_table_lacks_is_reported():
    """Synthetic: spdlog-vendor renamed gz-spdlog-vendor, as if Gazebo vendored it.

    gz-math-vendor wraps a gz library and is not reported. gz-utils-vendor and
    gz-cmake-vendor are absent from the trimmed index, so nothing is said of them.
    """
    text = fixture_text("dep-ros-resolute-amd64.txt").replace(
        "ros-lyrical-spdlog-vendor", "ros-lyrical-gz-spdlog-vendor"
    )
    reader = RosVendorDepsReader(FakeHttpClient().add_gzip(index("resolute"), text))
    assert reader.read([common_collection()]) == []
    assert reader.errors == [
        FetchError(
            "deps:aliases",
            "jetty/gz-common7 declares ros-lyrical-gz-spdlog-vendor (ros2) with no alias",
        )
    ]


def test_rolling_belongs_to_the_collection_whose_vendors_wait_in_ros2_testing():
    """Who owns Rolling is settled as the status engine settles it, staging included.

    The engine counts every Rolling vendor it fetched, so m owns Rolling as
    soon as its vendors reach ros2-testing, while ros2 still holds jetty's. Those
    must not come back as jetty's dependencies, and m has none until the sync:
    what a dependency gets is only ever read from ros2.
    """
    http = (
        FakeHttpClient()
        .add_gzip(index("noble"), fixture_text("dep-ros-noble-amd64.txt"))
        .add_gzip(index("resolute"), fixture_text("dep-ros-resolute-amd64.txt"))
        .add_gzip(staged_index("resolute"), fixture_text("dep-ros-testing-resolute-amd64.txt"))
        .add(madison("resolute"), fixture_text("dep-ros-madison-resolute.txt"))
    )
    records = RosVendorDepsReader(http).read([jetty("noble"), m()])
    assert {(r.collection, r.platform) for r in records} == {("jetty", "lyrical@resolute/amd64")}


def test_ros2_testing_is_read_only_to_settle_who_owns_a_rosdistro():
    """The same indexes ros_vendor reads, both channels, so the run's memo serves them."""
    http = FakeHttpClient()
    assert RosVendorDepsReader(http).read([jetty("noble"), m()]) == []
    assert http.requested == [
        f"{ROS2}/noble/main/binary-amd64/Packages.gz",
        f"{ROS2}/noble/main/binary-arm64/Packages.gz",
        f"{ROS2}/resolute/main/binary-amd64/Packages.gz",
        f"{ROS2}/resolute/main/binary-arm64/Packages.gz",
        f"{ROS2_TESTING}/noble/main/binary-amd64/Packages.gz",
        f"{ROS2_TESTING}/noble/main/binary-arm64/Packages.gz",
        f"{ROS2_TESTING}/resolute/main/binary-amd64/Packages.gz",
        f"{ROS2_TESTING}/resolute/main/binary-arm64/Packages.gz",
    ]


def test_the_reader_is_registered_for_ros():
    assert RosVendorDepsReader.system == "ros"
    assert "ros" in deps.available_readers()
