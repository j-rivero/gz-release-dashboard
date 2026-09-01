# gz-release-dashboard

Track the version of every Gazebo library across every packaging system that
ships it, and flag the ones lagging behind the released GitHub tag.

The dashboard covers each active collection (fortress, harmonic, ionic, jetty
and the in-development `m`) against five sources:

| column | source |
| --- | --- |
| `osrf deb` stable / prerelease | [packages.osrfoundation.org](http://packages.osrfoundation.org/gazebo), across every live Ubuntu release × amd64/arm64/armhf/i386 |
| `bazel` | the [Bazel Central Registry](https://bcr.bazel.build) |
| `conda` | [conda-forge](https://conda-forge.org), per subdir |
| `brew` | the [osrf/simulation](https://github.com/osrf/homebrew-simulation) tap, per bottle |
| `ros` ros2 / ros2-testing | vendor packages on [packages.ros.org](http://packages.ros.org) |

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
| · | the source was not fetched, or does not reach this collection |

A cell collapses every platform a source builds for. The worst status wins, so
one missing architecture cannot hide behind eleven green ones, and `(2/6)` says
how many platforms are affected. The web page expands the same cell into its
per-platform detail.

Three rules keep the noise down, all of them learned from the live data:

- **A platform must carry a real share of a collection** before it is held
  responsible for the rest. Majors are shared between collections (gz-tools 2
  belongs to harmonic, ionic and jetty alike), so a single leaked package must
  not drag a whole collection onto a distro it was never built for.
- **A library is only expected on an architecture the source builds it for.**
  gz-sim, gz-gui, gz-rendering, gz-launch and gz-sensors are absent from every
  armhf and i386 build by policy, not by oversight.
- **Staging channels are report-only.** `prerelease` and `ros2-testing` hold
  whatever happens to be queued at this instant, so a leftover release candidate
  older than the shipped version is stale rather than broken.

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
