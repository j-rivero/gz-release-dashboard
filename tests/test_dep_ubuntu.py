from conftest import FakeHttpClient, fixture_text

from gz_release_dashboard.deps.ubuntu import UbuntuResolver

MADISON = "https://people.canonical.com/~ubuntu-archive/madison.cgi"
ALL_NAMES = ["libdart-dev", "libbullet-dev", "libogre-1.9-dev", "libogre-next-dev", "libzenohc-dev"]
#: What the fixture was captured with.
FIXTURE_URL = (
    f"{MADISON}?package=libbullet-dev+libdart-dev+libogre-1.9-dev+libogre-next-dev+libzenohc-dev"
    "&s=jammy,jammy-updates,jammy-security,noble,noble-updates,noble-security,"
    "resolute,resolute-updates,resolute-security&a=amd64,arm64&text=on"
)


def fixture_resolver():
    http = FakeHttpClient().add(FIXTURE_URL, fixture_text("madison-deps.txt"))
    return UbuntuResolver(http), http


def test_one_request_covers_every_name_distro_pocket_and_arch():
    resolver, http = fixture_resolver()
    resolver.resolve(ALL_NAMES, ["jammy", "noble", "resolute"], ["amd64", "arm64"])
    assert http.requested == [FIXTURE_URL]


def test_versions_are_keyed_by_name_distro_and_arch():
    resolver, _ = fixture_resolver()
    versions = resolver.resolve(ALL_NAMES, ["jammy", "noble", "resolute"], ["amd64", "arm64"])
    assert versions[("libdart-dev", "noble", "arm64")] == "6.13.2+ds-0ubuntu3"
    assert versions[("libdart-dev", "resolute", "amd64")] == "6.13.2+ds-3fakesync1build7"
    assert versions[("libogre-next-dev", "jammy", "amd64")] == "2.2.5+dfsg3-0ubuntu2"
    # Ubuntu has no zenoh and no versioned dart names: absent, not empty.
    assert not any(name == "libzenohc-dev" for name, _, _ in versions)
    assert len(versions) == 24


def test_an_update_outranks_the_release_pocket_wherever_it_is_listed():
    url = f"{MADISON}?package=libdart-dev&s=noble,noble-updates,noble-security&a=amd64&text=on"
    # Synthetic: no gz dependency has an update in Ubuntu today.
    http = FakeHttpClient().add(
        url,
        " libdart-dev | 6.13.3+ds-0ubuntu1 | noble-updates/universe | amd64\n"
        " libdart-dev | 6.13.2+ds-0ubuntu3 | noble/universe         | amd64\n",
    )
    versions = UbuntuResolver(http).resolve(["libdart-dev"], ["noble"], ["amd64"])
    assert versions == {("libdart-dev", "noble", "amd64"): "6.13.3+ds-0ubuntu1"}


def test_an_architecture_nobody_asked_for_is_ignored():
    url = f"{MADISON}?package=libbullet-dev&s=noble,noble-updates,noble-security&a=amd64&text=on"
    http = FakeHttpClient().add(
        url, " libbullet-dev | 3.24+dfsg-2.1build1 | noble/universe | amd64, arm64, armhf\n"
    )
    versions = UbuntuResolver(http).resolve(["libbullet-dev"], ["noble"], ["amd64"])
    assert versions == {("libbullet-dev", "noble", "amd64"): "3.24+dfsg-2.1build1"}


def test_no_names_means_no_request():
    http = FakeHttpClient()
    assert UbuntuResolver(http).resolve([], ["noble"], ["amd64"]) == {}
    assert http.requested == []
