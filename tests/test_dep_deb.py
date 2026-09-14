import requests
from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard import config
from gz_release_dashboard.deps.deb_control import DebControlReader
from gz_release_dashboard.deps.ubuntu import madison_url
from gz_release_dashboard.models import Collection, FetchError, Library
from gz_release_dashboard.sources.debian_repo import packages_url

# Fixtures are live captures from 2026-09-14, trimmed. dep-deb-<repo>-control.txt
# keep the source stanza and the first binary stanza of ubuntu/debian/control;
# dep-deb-control-link.txt is the body of <distro>/debian/control, identical in
# all three repositories; dep-deb-osrf-<distro>-<arch>.txt keep only the stanzas
# these tests resolve, and only their Package, Source, Version and Architecture;
# dep-deb-madison.txt is madison's reply for every name declared here. Anything
# hand-made is marked synthetic where it is used.

RELEASE = "https://raw.githubusercontent.com/gazebo-release"
MADISON = "https://people.canonical.com/~ubuntu-archive/madison.cgi"
ARCHES = ("amd64", "arm64")


def control_url(repo, directory):
    return f"{RELEASE}/{repo}/main/{directory}/debian/control"


def serve_release(http, repo, fixture, distros=(), control=None):
    """ubuntu/debian/control, and each of ``distros`` as the link pointing at it."""
    http.add(control_url(repo, "ubuntu"), control if control is not None else fixture_text(fixture))
    for distro in distros:
        http.add(control_url(repo, distro), fixture_text("dep-deb-control-link.txt"))


def serve_osrf(http, distros, synthetic=None):
    """The stable indexes, with ``{(distro, arch): stanza}`` appended to them."""
    for distro in distros:
        for arch in ARCHES:
            text = fixture_text(f"dep-deb-osrf-{distro}-{arch}.txt")
            extra = (synthetic or {}).get((distro, arch))
            http.add_gzip(
                packages_url(config.OSRF_DEB_CHANNELS["stable"], distro, arch),
                f"{text}\n{extra}" if extra else text,
            )


def serve_madison(http, names, distros, reply=None):
    """Answer the one batched query from the capture, unless ``reply`` is given.

    madison replies one line per name, version and suite, so its reply to a
    narrower query is the capture's lines for those names and distros.
    """
    suites = [f"{distro}{pocket}" for distro in distros for pocket in ("", "-updates", "-security")]
    if reply is None:
        reply = "".join(
            f"{line}\n"
            for line in fixture_text("dep-deb-madison.txt").splitlines()
            if line.split("|")[0].strip() in names
            and line.split("|")[2].strip().split("/")[0] in distros
        )
    http.add(madison_url(sorted(names), suites, list(ARCHES)), reply)


def serve_rendering10(http, synthetic=None):
    serve_release(
        http, "gz-rendering10-release", "dep-deb-gz-rendering10-control.txt", ["noble", "resolute"]
    )
    serve_osrf(http, ["noble", "resolute"], synthetic)
    serve_madison(http, {"libogre-1.9-dev", "libogre-next-2.3-dev"}, ["noble", "resolute"])


def jetty(*libraries, distros=("noble", "resolute")):
    # gz-cmake is always there, as upstream: it is what makes libgz-cmake5-dev,
    # which the osrf fixtures carry, a gz library rather than an unmapped name.
    return Collection(
        "jetty",
        False,
        [Library("gz-cmake", 5)] + [Library(name, major) for name, major in libraries],
        list(distros),
    )


def stanza(package, source, version, arch):
    return f"Package: {package}\nSource: {source}\nVersion: {version}\nArchitecture: {arch}\n"


def rows(records):
    """Comparable tuples; the length check keeps a duplicate from hiding in the set."""
    projected = {
        (r.collection, r.library, r.major, r.dependency)
        + (r.platform, r.declared, r.version, r.origin)
        for r in records
    }
    assert len(projected) == len(records)
    return projected


def test_jetty_ogre_next_is_osrf_2_3_1_on_noble_and_2_3_3_on_resolute():
    """The expected jetty cell from the design, through link-body control files.

    noble/ and resolute/ both hold only ``../../ubuntu/debian/control``. Ubuntu
    has no libogre-next-2.3-dev, so osrf alone answers for ogre-next, while
    libogre-1.9-dev is Ubuntu's alone.
    """
    http = FakeHttpClient()
    serve_rendering10(http)
    records = DebControlReader(http).read([jetty(("gz-rendering", 10))])
    lib = ("jetty", "gz-rendering", 10)
    assert rows(records) == {
        (*lib, "ogre-next", "noble/amd64", "libogre-next-2.3-dev", "2.3.1", "osrf"),
        (*lib, "ogre-next", "noble/arm64", "libogre-next-2.3-dev", "2.3.1", "osrf"),
        (*lib, "ogre-next", "resolute/amd64", "libogre-next-2.3-dev", "2.3.3", "osrf"),
        (*lib, "ogre-next", "resolute/arm64", "libogre-next-2.3-dev", "2.3.3", "osrf"),
        (*lib, "ogre", "noble/amd64", "libogre-1.9-dev", "1.9.0", "ubuntu"),
        (*lib, "ogre", "noble/arm64", "libogre-1.9-dev", "1.9.0", "ubuntu"),
        (*lib, "ogre", "resolute/amd64", "libogre-1.9-dev", "1.9.0", "ubuntu"),
        (*lib, "ogre", "resolute/arm64", "libogre-1.9-dev", "1.9.0", "ubuntu"),
    }


def read_physics9(control=None, synthetic=None):
    http = FakeHttpClient()
    serve_release(
        http,
        "gz-physics9-release",
        "dep-deb-gz-physics9-control.txt",
        ["noble", "resolute"],
        control=control,
    )
    serve_osrf(http, ["noble", "resolute"], synthetic)
    serve_madison(http, {"libbullet-dev", "libdart6.16-dev"}, ["noble", "resolute"])
    reader = DebControlReader(http)
    return reader, reader.read([jetty(("gz-physics", 9))])


def test_the_declared_dart_series_is_resolved_by_its_exact_binary_name():
    """osrf noble carries libdart6.13-dev and libdart6.16-dev side by side.

    gz-physics9 declares ``libdart6.16-dev [!armhf]``, below a ``#`` comment
    line inside Build-Depends: amd64 and arm64 both get 6.16.6, never 6.13.2.
    """
    _, records = read_physics9()
    lib = ("jetty", "gz-physics", 9)
    assert rows(records) == {
        (*lib, "dart", "noble/amd64", "libdart6.16-dev", "6.16.6", "osrf"),
        (*lib, "dart", "noble/arm64", "libdart6.16-dev", "6.16.6", "osrf"),
        (*lib, "dart", "resolute/amd64", "libdart6.16-dev", "6.16.6", "osrf"),
        (*lib, "dart", "resolute/arm64", "libdart6.16-dev", "6.16.6", "osrf"),
        (*lib, "bullet", "noble/amd64", "libbullet-dev", "3.24", "ubuntu"),
        (*lib, "bullet", "noble/arm64", "libbullet-dev", "3.24", "ubuntu"),
        (*lib, "bullet", "resolute/amd64", "libbullet-dev", "3.24", "ubuntu"),
        (*lib, "bullet", "resolute/arm64", "libbullet-dev", "3.24", "ubuntu"),
    }


def test_a_comment_with_a_colon_inside_build_depends_hides_nothing():
    # Synthetic: the live comment has no colon, which is the only reason it is
    # harmless to a stanza parser that knows nothing of comments.
    original = fixture_text("dep-deb-gz-physics9-control.txt")
    control = original.replace("# DART from packages.o.o", "# DART: from packages.o.o")
    assert control != original
    _, records = read_physics9(control=control)
    assert {r.platform for r in records if r.dependency == "dart"} == {
        "noble/amd64",
        "noble/arm64",
        "resolute/amd64",
        "resolute/arm64",
    }


def test_an_architecture_qualifier_leaves_the_excluded_architecture_undeclared():
    # Synthetic: the live qualifier is [!armhf], which excludes nothing we query.
    original = fixture_text("dep-deb-gz-physics9-control.txt")
    control = original.replace("libdart6.16-dev [!armhf]", "libdart6.16-dev [!arm64]")
    assert control != original
    _, records = read_physics9(control=control)
    assert {r.platform for r in records if r.dependency == "dart"} == {
        "noble/amd64",
        "resolute/amd64",
    }


def test_the_higher_of_osrf_and_ubuntu_wins_and_a_tie_goes_to_osrf():
    """apt installs the higher version, so that is the one a build gets.

    Synthetic: osrf carries no libbullet-dev; one is added above Ubuntu's 3.24
    on noble/amd64, below it on noble/arm64 and level with it on
    resolute/amd64. resolute/arm64 is left to Ubuntu alone.
    """
    def bullet(version, arch):
        return stanza("libbullet-dev", "bullet", version, arch)

    _, records = read_physics9(
        synthetic={
            ("noble", "amd64"): bullet("3.25+dfsg-1~osrf1~noble", "amd64"),
            ("noble", "arm64"): bullet("3.06+dfsg-1~osrf1~noble", "arm64"),
            ("resolute", "amd64"): bullet("3.24+dfsg-1~osrf1~resolute", "amd64"),
        }
    )
    assert {(r.platform, r.version, r.origin) for r in records if r.dependency == "bullet"} == {
        ("noble/amd64", "3.25", "osrf"),
        ("noble/arm64", "3.24", "ubuntu"),
        ("resolute/amd64", "3.24", "osrf"),
        ("resolute/arm64", "3.24", "ubuntu"),
    }


def test_an_index_holding_a_binary_twice_counts_as_its_newest_stanza():
    # Synthetic: an older stanza after the real one on amd64 and a newer one on
    # arm64, so neither the first nor the last stanza read passes for the newest.
    http = FakeHttpClient()
    serve_rendering10(
        http,
        synthetic={
            ("noble", "amd64"): stanza(
                "libogre-next-2.3-dev", "ogre-next-2.3", "2.3.0-1osrf~noble", "amd64"
            ),
            ("noble", "arm64"): stanza(
                "libogre-next-2.3-dev", "ogre-next-2.3", "2.3.2-1osrf~noble", "arm64"
            ),
        },
    )
    records = DebControlReader(http).read([jetty(("gz-rendering", 10))])
    assert {
        (r.platform, r.version)
        for r in records
        if r.dependency == "ogre-next" and r.platform.startswith("noble/")
    } == {("noble/amd64", "2.3.1"), ("noble/arm64", "2.3.2")}


def read_ign_rendering6(synthetic=None, ubuntu_reply=None):
    http = FakeHttpClient()
    serve_release(http, "ign-rendering6-release", "dep-deb-ign-rendering6-control.txt", ["jammy"])
    serve_osrf(http, ["jammy"], synthetic)
    serve_madison(
        http,
        {"libogre-1.9-dev", "libogre-2.2-dev", "libogre-next-dev"},
        ["jammy"],
        reply=ubuntu_reply,
    )
    fortress = Collection("fortress", False, [Library("gz-rendering", 6)], ["jammy"])
    return http, DebControlReader(http).read([fortress])


def test_an_ignition_era_repository_with_the_second_alternative_resolving():
    """ign-rendering6 declares ``libogre-2.2-dev | libogre-next-dev``.

    Neither osrf jammy nor Ubuntu has libogre-2.2-dev, so Ubuntu's
    libogre-next-dev 2.2.5 is what the build gets. The repository is found
    under its ignition-era name after the two newer spellings 404. (Live,
    gz-rendering6-release answers too, as a rename; it is withheld here.)
    """
    http, records = read_ign_rendering6()
    lib = ("fortress", "gz-rendering", 6)
    assert rows(records) == {
        (*lib, "ogre", "jammy/amd64", "libogre-1.9-dev", "1.9.0", "ubuntu"),
        (*lib, "ogre", "jammy/arm64", "libogre-1.9-dev", "1.9.0", "ubuntu"),
        (*lib, "ogre-next", "jammy/amd64", "libogre-next-dev", "2.2.5", "ubuntu"),
        (*lib, "ogre-next", "jammy/arm64", "libogre-next-dev", "2.2.5", "ubuntu"),
    }
    probed = [u for u in http.requested if u.endswith("/main/ubuntu/debian/control")]
    assert probed[:3] == [
        control_url("gz-rendering6-release", "ubuntu"),
        control_url("ignition-rendering6-release", "ubuntu"),
        control_url("ign-rendering6-release", "ubuntu"),
    ]


def test_the_first_alternative_that_resolves_is_the_one_reported():
    # Synthetic: osrf jammy has no libogre-2.2-dev; it is given one on amd64 only.
    _, records = read_ign_rendering6(
        synthetic={
            ("jammy", "amd64"): stanza(
                "libogre-2.2-dev", "ogre-2.2", "2.2.6+20211021-1~jammy", "amd64"
            )
        }
    )
    ogre_next = [r for r in records if r.dependency == "ogre-next"]
    assert {(r.platform, r.declared, r.version, r.origin) for r in ogre_next} == {
        ("jammy/amd64", "libogre-2.2-dev", "2.2.6", "osrf"),
        ("jammy/arm64", "libogre-next-dev", "2.2.5", "ubuntu"),
    }


def test_a_declaration_nothing_resolves_is_still_a_record_with_no_version():
    """It shows as ``?`` rather than vanishing, named by its first alternative.

    Synthetic: Ubuntu answers nothing, so neither ogre name resolves on jammy.
    """
    _, records = read_ign_rendering6(ubuntu_reply="")
    lib = ("fortress", "gz-rendering", 6)
    assert rows(records) == {
        (*lib, "ogre", "jammy/amd64", "libogre-1.9-dev", None, ""),
        (*lib, "ogre", "jammy/arm64", "libogre-1.9-dev", None, ""),
        (*lib, "ogre-next", "jammy/amd64", "libogre-2.2-dev", None, ""),
        (*lib, "ogre-next", "jammy/arm64", "libogre-2.2-dev", None, ""),
    }


def test_with_no_distro_control_file_ubuntu_applies_to_the_declared_distros():
    """Synthetic: the noble/ and resolute/ links are withheld.

    resolute is live, through m, but jetty declares only noble, so that is the
    one distribution ubuntu/debian/control is taken to build for.
    """
    http = FakeHttpClient()
    serve_release(http, "gz-rendering10-release", "dep-deb-gz-rendering10-control.txt")
    serve_osrf(http, ["noble", "resolute"])
    serve_madison(http, {"libogre-1.9-dev", "libogre-next-2.3-dev"}, ["noble", "resolute"])
    m = Collection("m", True, [Library("gz-sim", 11)], ["resolute"])
    records = DebControlReader(http).read([jetty(("gz-rendering", 10), distros=["noble"]), m])
    lib = ("jetty", "gz-rendering", 10)
    assert rows(records) == {
        (*lib, "ogre-next", "noble/amd64", "libogre-next-2.3-dev", "2.3.1", "osrf"),
        (*lib, "ogre-next", "noble/arm64", "libogre-next-2.3-dev", "2.3.1", "osrf"),
        (*lib, "ogre", "noble/amd64", "libogre-1.9-dev", "1.9.0", "ubuntu"),
        (*lib, "ogre", "noble/arm64", "libogre-1.9-dev", "1.9.0", "ubuntu"),
    }


def test_a_link_that_does_not_settle_within_two_hops_skips_that_distro():
    """Synthetic chains: resolute reaches ubuntu/debian/control in two links and
    is read; noble would need three and is reported instead."""
    repo = "gz-rendering10-release"
    http = FakeHttpClient()
    serve_release(http, repo, "dep-deb-gz-rendering10-control.txt")
    http.add(control_url(repo, "resolute"), "../../mid/debian/control")
    http.add(control_url(repo, "mid"), "../../ubuntu/debian/control\n")
    http.add(control_url(repo, "noble"), "../../a/debian/control")
    http.add(control_url(repo, "a"), "../../b/debian/control")
    http.add(control_url(repo, "b"), "../../ubuntu/debian/control")
    serve_osrf(http, ["noble", "resolute"])
    serve_madison(http, {"libogre-1.9-dev", "libogre-next-2.3-dev"}, ["noble", "resolute"])
    reader = DebControlReader(http)
    records = reader.read([jetty(("gz-rendering", 10))])
    assert {r.platform for r in records} == {"resolute/amd64", "resolute/arm64"}
    [error] = reader.errors
    assert error.source == "deps:deb"
    assert "gz-rendering10-release" in error.message
    assert "noble/debian/control" in error.message


class UnreachableMadison(FakeHttpClient):
    def get_bytes(self, url, *, ok_404=False):
        if url.startswith(MADISON):
            self.requested.append(url)
            raise requests.ConnectionError(f"cannot reach {url}")
        return super().get_bytes(url, ok_404=ok_404)


def test_an_unreachable_madison_keeps_the_osrf_versions_and_says_so():
    http = UnreachableMadison()
    serve_rendering10(http)
    reader = DebControlReader(http)
    records = reader.read([jetty(("gz-rendering", 10))])
    assert {
        (r.platform, r.version, r.origin) for r in records if r.dependency == "ogre-next"
    } == {
        ("noble/amd64", "2.3.1", "osrf"),
        ("noble/arm64", "2.3.1", "osrf"),
        ("resolute/amd64", "2.3.3", "osrf"),
        ("resolute/arm64", "2.3.3", "osrf"),
    }
    # libogre-1.9-dev was Ubuntu's alone: unresolved now, not dropped.
    assert {(r.version, r.origin) for r in records if r.dependency == "ogre"} == {(None, "")}
    [error] = reader.errors
    assert error.source == "deps:ubuntu"
    assert "not consulted" in error.message


def test_ubuntu_is_asked_once_for_every_name_every_build_declares():
    http = FakeHttpClient()
    serve_release(
        http, "gz-physics9-release", "dep-deb-gz-physics9-control.txt", ["noble", "resolute"]
    )
    serve_release(
        http, "gz-rendering10-release", "dep-deb-gz-rendering10-control.txt", ["noble", "resolute"]
    )
    serve_osrf(http, ["noble", "resolute"])
    serve_madison(
        http,
        {"libbullet-dev", "libdart6.16-dev", "libogre-1.9-dev", "libogre-next-2.3-dev"},
        ["noble", "resolute"],
    )
    DebControlReader(http).read([jetty(("gz-physics", 9), ("gz-rendering", 10))])
    assert [u for u in http.requested if u.startswith(MADISON)] == [
        f"{MADISON}?package=libbullet-dev+libdart6.16-dev+libogre-1.9-dev+libogre-next-2.3-dev"
        "&s=noble,noble-updates,noble-security,resolute,resolute-updates,resolute-security"
        "&a=amd64,arm64&text=on"
    ]


def test_an_osrf_hosted_name_with_no_alias_is_reported_once_per_build():
    """Synthetic: gz-physics9 declaring libfcl-dev, which osrf is made to host.

    It is seen on four distro and architecture indexes and reported once.
    """
    original = fixture_text("dep-deb-gz-physics9-control.txt")
    control = original.replace("libbullet-dev,", "libbullet-dev,\n               libfcl-dev,")
    assert control != original
    reader, records = read_physics9(
        control=control,
        synthetic={
            (distro, arch): stanza("libfcl-dev", "fcl", f"0.7.0-1~osrf1~{distro}", arch)
            for distro in ("noble", "resolute")
            for arch in ARCHES
        },
    )
    assert reader.errors == [
        FetchError("deps:aliases", "jetty/gz-physics9 declares libfcl-dev (osrf) with no alias")
    ]
    assert all(r.declared != "libfcl-dev" for r in records)


def test_gz_libraries_and_components_of_a_tracked_source_are_not_reported():
    """gz-physics9 declares seven libdart6.16-* components beside libdart6.16-dev.

    osrf hosts them all as Source: dart, and none has an alias, but none means
    the table has fallen behind: dart is tracked through libdart6.16-dev. The
    same goes for libgz-cmake5-dev, a gz library. Only the first component is
    in the trimmed index, which is enough to be reported if it were going to be.
    """
    reader, _ = read_physics9()
    assert reader.errors == []


def test_a_major_shared_by_several_collections_gets_records_in_each():
    """The distro control files say where a library is built, not the collection's distros.

    A collection's distros come from its release jobs' packaging configs, which
    name the one distro a job builds on: jetty lists noble alone, while osrf
    publishes gz-rendering10 on resolute too. Narrowing to them once dropped
    every resolute record jetty has, and with it the ogre-next 2.3.1–2.3.3 ⚠.
    """
    http = FakeHttpClient()
    serve_rendering10(http)
    m = Collection("m", True, [Library("gz-rendering", 10)], ["resolute"])
    records = DebControlReader(http).read([jetty(("gz-rendering", 10), distros=["noble"]), m])
    assert {(r.collection, r.platform) for r in records if r.dependency == "ogre-next"} == {
        ("jetty", "noble/amd64"),
        ("jetty", "noble/arm64"),
        ("jetty", "resolute/amd64"),
        ("jetty", "resolute/arm64"),
        ("m", "noble/amd64"),
        ("m", "noble/arm64"),
        ("m", "resolute/amd64"),
        ("m", "resolute/arm64"),
    }


def test_a_collection_the_osrf_repository_does_not_publish_gets_no_records(monkeypatch):
    monkeypatch.setitem(config.COLLECTION_SOURCES_EXCLUDED, "m", frozenset({"osrf_debian"}))
    http = FakeHttpClient()
    serve_rendering10(http)
    m = Collection("m", True, [Library("gz-rendering", 10)], ["resolute"])
    records = DebControlReader(http).read([jetty(("gz-rendering", 10), distros=["noble"]), m])
    assert records
    assert {r.collection for r in records} == {"jetty"}


def test_a_library_with_no_release_repository_declares_nothing():
    http = FakeHttpClient()
    reader = DebControlReader(http)
    assert reader.read([jetty(("gz-sim", 10))]) == []
    assert reader.errors == []
    assert not any(u.startswith(MADISON) for u in http.requested)
