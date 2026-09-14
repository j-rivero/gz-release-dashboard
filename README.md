# gz-release-dashboard

Track the version of every Gazebo library across every packaging system that
ships it, and flag the ones lagging behind the released GitHub tag.

The dashboard covers each active collection (fortress, harmonic, ionic, jetty
and the in-development `m`) against six sources:

| column | source |
| --- | --- |
| `osrf deb` stable / prerelease | [packages.osrfoundation.org](http://packages.osrfoundation.org/gazebo), every live Ubuntu release × amd64/arm64 |
| `bazel` | the [Bazel Central Registry](https://bcr.bazel.build) |
| `conda` | [conda-forge](https://conda-forge.org), per subdir |
| `brew` | the [osrf/simulation](https://github.com/osrf/homebrew-simulation) tap, per bottle |
| `ros vendor` ros2 / ros2-testing | vendor packages on [packages.ros.org](http://packages.ros.org) |
| `ros deb` bootstrap / stable | the gz packages themselves, imported into [repos.ros.org/repos/ros_bootstrap](http://repos.ros.org/repos/ros_bootstrap) and [packages.ros.org/ros2/ubuntu](http://packages.ros.org/ros2/ubuntu) |

Not every source reaches every collection, so the tables do not all have the
same columns — see [Sources reach different collections](#sources-reach-different-collections).

Ground truth is the release tags pushed to the `gazebosim` GitHub repositories,
for the libraries listed in
[gz-collections.yaml](https://github.com/gazebo-tooling/release-tools/blob/master/jenkins-scripts/dsl/gz-collections.yaml).
The nightly repository, the collection metapackages and the `rotary` collection
are all out of scope.

### End-of-life distributions exclude themselves

Which Ubuntu releases get queried is derived per run from the `packaging.configs`
each live collection declares in `gz-collections.yaml`, resolved through
`packaging_configs[].system`. Nothing in this repository names a distribution.

That means focal is already absent — no live collection packages for it any more
— and jammy will drop out on its own the day fortress is retired upstream, with
no change here. The same list drives the ROS vendor queries, since a ROS distro
only matters while Gazebo still packages for the Ubuntu release underneath it.

The union across collections is what counts, never the per-collection list:
upstream under-declares it. jetty names only `noble` yet ships on resolute too,
so reading the declarations per collection would hide a real column.

## Usage

```console
$ uv venv && uv sync
$ uv run gz-dashboard fetch                 # writes snapshot.json (~4 min, network)
$ uv run gz-dashboard console               # colourful terminal dashboard
$ uv run gz-dashboard html -o public/       # static page for GitHub Pages
$ uv run gz-dashboard all -o public/        # fetch, report, publish
```

Fetching and rendering are separate on purpose: `fetch` is the only step that
touches the network, and every renderer works offline from the snapshot, so you
can re-slice a single fetch as many times as you like.

```console
$ uv run gz-dashboard console --collection jetty --source osrf_debian --verbose
$ uv run gz-dashboard console --problems-only --fail-on-problems
$ uv run gz-dashboard fetch --cache-dir .cache   # memoise HTTP bodies while iterating
```

`--fail-on-problems` exits 1 when anything is behind or missing. It is off by
default so a lagging package never blocks a deploy.

## Reading the output

| glyph | meaning |
| --- | --- |
| ✅ | matches the latest release tag |
| 🔶 | behind the latest release tag |
| ❌ | not published where it was expected |
| ⬆️ | ahead of the latest tag (reported, never a problem) |
| — | never expected here |
| · | the source was not fetched, or has nothing for this library |

A cell collapses every platform a source builds for. The worst status wins, so
one missing architecture cannot hide behind eleven green ones, and `(2/6)` says
how many platforms are affected. The web page expands the same cell into its
per-platform detail.

Seven rules keep the noise down, all of them learned from the live data:

- **A platform must carry a real share of a collection** before it is held
  responsible for the rest. Majors are shared between collections (gz-tools 2
  belongs to harmonic, ionic and jetty alike), so a single leaked package must
  not drag a whole collection onto a distro it was never built for.
- **Only amd64 and arm64 are queried.** Gazebo does not support i386, and armhf
  production is being retired. Packages for either still sit in the index, but a
  leftover read as evidence that an architecture is built is exactly what turns a
  deliberate drop into a reported gap. This is the one list that cannot be
  derived from `gz-collections.yaml`, whose `packaging_configs` name only the
  architecture the release job builds *on*, not what the repository publishes.
- **A library is only expected on an architecture the source builds it for.**
  gz-sim, gz-gui, gz-launch, gz-sensors and others have no Intel-Mac bottle in
  homebrew and no ppc64le build in conda-forge — policy, not oversight. Now that
  the Debian side is amd64/arm64 only, this rule does its work on the macOS and
  conda platforms.
- **The osrf `prerelease` repository is an overlay on `stable`, not a repository
  of its own.** Both are enabled together and apt installs whichever version is
  higher, so an entry counts only while it is ahead of the highest stable version
  of that major; at or below it, it is the release candidate of a release that
  already shipped, and is dropped — on every architecture, since lingering on the
  one architecture stable never built for is exactly how such candidates survive.
  What is left is a release on its way out — exactly what the channel should hold
  — so the column shows a version only when something is genuinely queued, and
  shows it green. Empty is the normal state, and a release going straight to
  stable with no candidate at all is normal too.
  `ros2-testing` is deliberately not treated this way: it is a full repository
  that a sync drains into `ros2`, so being behind there is real.
- **ROS Rolling belongs to the newest collection only.** Rolling tracks whatever
  Gazebo is newest, and it is slow to let the previous generation go: it
  currently carries 31 vendor packages, all of jetty's and all of m's. Scoring
  jetty against it would report a permanent lag that no jetty release can fix,
  because jetty's vendor packages live in `lyrical` now. Every other ROS distro
  is pinned to one collection and stays with it. The result is one ROS
  distribution per collection: harmonic→jazzy, ionic→kilted, jetty→lyrical,
  m→rolling.
- **Staging channels are report-only.** Nothing on `prerelease` or
  `ros2-testing` ever counts as a problem or moves the exit code.
- **A source only answers for the collections it publishes.** Declared in
  `config.COLLECTION_SOURCES_EXCLUDED` / `COLLECTION_SOURCES_ONLY`, and asked
  once through `config.source_applies`, so being listed and being scored are
  the same fact: a source that does not apply gets no column, no cells and no
  problems. Fortress predates Bazel, conda-forge and the ROS vendor packages,
  and is the only collection ROS carries the gz packages themselves for;
  harmonic predates the Bazel registry, whose oldest modules are ionic's.

### Sources reach different collections

Each collection's table carries the columns of the sources that publish it, so
fortress and jetty do not have the same header. Fortress is the ignition
generation: there is no Bazel module, no conda-forge build and no ROS vendor
package for it, and columns that can only ever be empty read as gaps. What it
does have is the two Debian repositories the ROS world installs from, which
carry the gz source packages themselves rather than vendor wrappers —
`ros_bootstrap`, what the ROS buildfarm builds against, and `ros2/ubuntu`, what
a user apt-gets. A Gazebo release has only really reached ROS once both agree
with packages.osrfoundation.org, so neither is treated as a staging channel and
being behind in either is reported.

The same is true one collection later, for one column: the Bazel Central
Registry's oldest gz modules are ionic's majors, so harmonic has no Bazel
column either.

Where a source applies is the one thing here that is declared rather than
derived, in `config.COLLECTION_SOURCES_EXCLUDED` and `COLLECTION_SOURCES_ONLY`.
It also narrows the queries: a Debian source takes its distribution list from
the collections it is handed, so the ROS import asks for jammy and nothing else.

## Dependencies

Under each library table sits a second one: the third-party packages that the
collection's builds declare, one column per build system — `deb`, `bazel`,
`conda`, `brew` and `ros vendor`. It is an inventory, not a verdict. There is no
expected version for a dependency, so nothing in it is ever a problem or moves
the exit code.

Every link between a collection and a dependency is read from the build files,
so nobody maintains a list of who uses what:

| system | declared in | version from |
| --- | --- | --- |
| deb | `Build-Depends` of the gazebo-release `debian/control` | packages.osrfoundation.org, or Ubuntu when its version is higher |
| bazel | `bazel_dep` in the module's `MODULE.bazel` | the pin itself |
| conda | `depends` of the `libgz-*` conda-forge artifact | the floor of the pin: what the package was built against |
| brew | `depends_on` in the osrf/simulation formula | the tap's formula, else homebrew-core |
| ros vendor | `Depends` of the `ros-<distro>-gz-*-vendor` package | the dependency's own vendor package, or Ubuntu |

Only dependencies Gazebo packages somewhere are tracked — ogre, ogre-next,
dart, bullet, zenoh and mujoco — each named once in `config.DEPENDENCY_ALIASES`
with the spelling every system uses for it. A Gazebo-hosted name that matches no
alias is reported as a `deps:aliases` fetch error, so a new one cannot slip by.

| mark | meaning |
| --- | --- |
| ⚠ | one system carries several versions across its platforms or declarations: osrf noble still on ogre-next 2.3.1 while resolute has 2.3.3, shown as `2.3.1–2.3.3`. The page lists these under *dependency divergence* |
| ◇ | systems disagree on the series (major.minor): conda-forge building dart 6.19 while the Debian side ships 6.16. Often deliberate, and shown so it is known. A patch-only difference is not marked |

A reader follows its library source, so `--source conda_forge` fetches conda
libraries and conda dependencies alike. The marks are settled on the whole
snapshot before `--collection`, `--source` or `--lib` narrow it, so hiding a
system never takes away the ◇ it was part of.

## Adding a source

Sources are a factory registry. Drop a module in `src/gz_release_dashboard/sources/`,
decorate the class with `@register_source`, and import it at the bottom of
`sources/__init__.py`. The `--source` choices, the fetch loop and the renderer
columns all follow automatically.

```python
@register_source
class MySource(PackageSource):
    name = "my_source"
    channels = ("stable",)          # or () for a source with no channels

    def fetch(self, collections: list[Collection]) -> list[PackageRecord]:
        ...
```

A Debian repository is less than that. `sources/debian_repo.py` holds the walk
over channels × distributions × architectures (`AptSource`) and, on top of it,
the reading of gz source packages — the `-dbgsym` and alias filters, the newest
stanza of a binary, the oldest binary of a source (`GzAptSource`). Both
packages.osrfoundation.org and the ROS import declare their repositories and
nothing else:

```python
@register_source
class RosGzDebianSource(GzAptSource):
    name = "ros_gz_debian"
    channels = ("bootstrap", "stable")
    repositories = config.ROS_GZ_DEB_CHANNELS   # channel -> repository root
    arches = config.ROS_DEB_ARCHES
```

Sources take their HTTP client by constructor injection, so the tests drive
them entirely from fixtures with no network access.

## Development

```console
$ uv run pytest
```

The suite is fully offline. Every gotcha the live data threw up has a fixture
and an explicit assertion: `-dbgsym` twins, `gz-jetty-*` alias packages,
`10.1.1-1.995~noble` packaging revisions, `.bcr.N` registry repacks, yanked BCR
versions, `gz-fuel_tools10` underscores, `sdformat-vendor`'s missing `gz-`
prefix, head-only brew formulas, and the ignition-era naming throughout.

## Publishing

`.github/workflows/dashboard.yml` fetches and deploys to GitHub Pages daily at
05:17 UTC, and on demand via *Run workflow*. The published dashboard lives at
<https://j-rivero.github.io/gz-release-dashboard/>.

Pages has to be told to take its content from the workflow. This repository is
already configured; a fork needs the setting once, either in **Settings → Pages**
by setting **Source** to **GitHub Actions**, or with:

```console
$ gh api --method POST repos/OWNER/REPO/pages -f build_type=workflow
```

`.github/workflows/ci.yml` runs the test suite on every push and pull request.
