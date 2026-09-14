# Dependency inventory

Status: design agreed 2026-09-14, not implemented.

## Goal

Alongside the gz libraries, show which version of each dependency Gazebo
packages itself (ogre-next, ogre 1.x, dart, bullet, zenoh, mujoco) every
collection gets from every packaging system, and mark where those versions
disagree.

This is an inventory. No dependency cell is ever "behind" or "missing", and
nothing here feeds the problems panel or `--fail-on-problems`. A dependency has
no release tag to be measured against; the signal worth having is disagreement.

## Why the library pipeline does not fit

- There is no ground truth. gz libraries are scored against the tags pushed to
  `gazebosim`; nobody in Gazebo tags dart.
- What a store holds is not what a collection uses. conda-forge holds 34 dartsim
  versions and BCR 4. Even a Debian repository, one version per binary name per
  distribution, holds several series side by side because the series is in the
  name: osrf noble carries both `libdart6.13-dev` and `libdart6.16-dev`. What
  matters is what a collection's build *declares* and what that declaration
  *resolves to*.
- `PackageRecord` is keyed on `(library, major)`, and every rule in `engine.py`
  (tag comparison, platform share, overlay channels, absence) is about releases.

## Decisions

| # | decision | rejected |
| --- | --- | --- |
| 1 | Inventory only. ⚠ when platforms of one system disagree, ◇ when systems disagree on the series | pass/fail against a requirement; staleness against the dependency's own releases |
| 2 | The per-collection link is derived from each build system's own declaration | a curated per-collection YAML; a table not tied to collections |
| 3 | Track only dependencies Gazebo packages or vendors, through one alias table | a hand-picked list of system deps; every declared dependency |
| 4 | Read the base archives too: Ubuntu under osrf, homebrew-core under the tap | Gazebo-hosted repositories only |
| 5 | A separate `deps/` subsystem; the library pipeline is untouched | `fetch_dependencies()` on every `PackageSource` |
| 6 | conda shows the pin floor, the version the gz package was built against | the newest build inside the pin |
| 7 | The snapshot schema stays at 1; `dependencies` is an additive field | bumping to 2 |

## Evidence

Live data as of 2026-09-14. These are the formats the readers must handle, and
the seeds for their fixtures.

- `gz-collections.yaml` declares no dependencies.
- **gazebo-release.** `gz-physics9-release` has `noble/debian/control` and
  `resolute/debian/control`, whose raw bodies are the one-line link
  `../../ubuntu/debian/control`. Its Build-Depends name `libdart6.16-dev [!armhf]`
  and `libbullet-dev`. `ign-rendering6-release` declares
  `libogre-2.2-dev | libogre-next-dev`. `gz-transport15-release` declares
  `libzenohc-dev` and `libzenohcpp-dev`. Default branch `main` in all three.
- **osrf stable.** noble amd64 has `libdart6.13-dev 6.13.2+ds1-1~osrf2~noble`
  and `libdart6.16-dev 6.16.6+ds-1~osrf1~noble`. Source `ogre-next-2.3` is
  `2.3.1-9osrf~noble` on noble and `2.3.3+osrf1-4osrf~resolute` on resolute.
- **Ubuntu** (madison). `libdart-dev` 6.13.2 on noble and resolute,
  `libogre-next-dev` 2.3.3 (2.2.5 on jammy), `libbullet-dev` 3.24 (3.06 on
  jammy), `libogre-1.9-dev` 1.9.0. Ubuntu has no `libdart6.16-dev` and no
  `libogre-next-2.3-dev`. One request answers several packages
  (`package=a+b`), several suites and an architecture filter (`a=arm64`).
- **brew.** gz-rendering10 `depends_on "ogre1.9"`, `"ogre2.3"`;
  ignition-rendering6 `"ogre2.2"`; gz-physics9 `"dartsim"`, `"bullet"`, which
  are not in the tap and resolve through homebrew-core to 6.19.4 and 3.25. Tap
  version spellings: ogre2.3 `url ".../v2.3.1.tar.gz"`, ogre2.2
  `version "2.2.6+20211021~312bf40"`, ogre1.9 `version "1.9-20160714-<sha>"`,
  dartsim@6.10.0 `version "6.10.0~20211005~<sha>"`, bullet@2.87
  `url ".../2.87.tar.gz"`. ogre-next is not in homebrew-core.
- **conda.** The `gz-physics` package carries no pins; its `libgz-physics`
  output does. `libgz-physics` 9.5.1 depends on
  `dartsim-cpp >=6.19.4,<6.20.0a0` and `bullet-cpp >=3.25,<3.26.0a0`. Older
  majors live on the legacy names: `libgz-physics7` 7.5.0 and `libgz-physics8`
  8.3.0 pin `dartsim-cpp >=6.15.0,<6.16.0a0`, while the unversioned
  `libgz-physics` 7.5.0 has no tracked depends. `libgz-rendering` 10.0.2 pins
  `ogre >=1.10.12.1,<1.11.0a0` and `ogre-next >=2.3.3,<2.3.4.0a0`.
  `libgz-transport` 15.1.0 pins `libzenohc >=1.9.0,<1.9.1.0a0`.
- **BCR.** gz-physics 8.4.0 and 9.4.0 pin `dartsim 6.13.2.bcr.2`/`.bcr.3` and
  `bullet 3.26.0-rc0.bcr.1`. gz-rendering 9.4.0 pins `ogre-next 2.3.3`, and
  10.0.2 and 11.0.0-pre1 pin `ogre-next 2.3.3.bcr.6`. gz-transport pins no
  zenoh.
- **ROS.** `ros-lyrical-gz-physics-vendor` Depends on
  `ros-lyrical-gz-dartsim-vendor` and `libbullet-dev`;
  `ros-lyrical-gz-rendering-vendor` on `ros-lyrical-gz-ogre-next-vendor` and
  `libogre-1.9-dev`; the lyrical and rolling `gz-transport-vendor` on
  `zenoh-cpp-vendor`, the jazzy one does not. Descriptions:
  `Vendor package for the DART physics engine v6.16.6`,
  `Vendor package for Ogre-next v2.3.3`,
  `Vendor package for MuJoCo simulator of version 3.4.0`,
  `Vendor pkg to install zenoh-cpp` (no version). The `ros2-gbp` release tags
  agree with the descriptions (jazzy dart 6.13.2, lyrical dart 6.16.6, lyrical
  ogre-next 2.3.3), so the description is trusted.

## Architecture

```
fetch   library sources  --> snapshot.records        \  one HttpClient,
        dependency readers --> snapshot.dependencies /   memoised per run
render  engine          --> StatusEntry  --> library tables     (unchanged)
        deps.inventory  --> rows + marks --> dependency tables
```

New files, all under `src/gz_release_dashboard/`:

- `deps/__init__.py`: the `@register_reader` registry, `available_readers()`,
  `create_readers()`, mirroring `sources/__init__.py`.
- `deps/base.py`: `DependencyReader(ABC)` with `system`, `source` (the library
  source it follows) and `read(collections) -> list[DependencyRecord]`.
- `deps/aliases.py`: name matching against `config.DEPENDENCY_ALIASES`, and the
  alias check.
- `deps/ubuntu.py`: the batched madison resolver.
- `deps/deb_control.py`, `deps/brew_formula.py`, `deps/conda_artifacts.py`,
  `deps/bcr_module.py`, `deps/ros_vendor_deps.py`: one reader per system.
- `deps/inventory.py`: pure grouping and marks.

Changed files:

- `models.py`: `DependencyRecord`; `Snapshot.dependencies`.
- `versions.py`: `dependency_version()` and `series()`.
- `config.py`: `DEPENDENCY_ALIASES`, `DEPENDENCY_SYSTEMS`, the new URLs.
- `http.py`: the in-run memo.
- `snapshot.py`: reads `dependencies`.
- `engine.py`: the share test inside `rolling_collection` becomes a helper the
  ROS reader also uses.
- `sources/bazel_registry.py`: the newest-version-of-a-major selection becomes a
  function the BCR reader also uses.
- `cli.py`, `render/console.py`, `render/html.py`, the template, `README.md`.

## Data model

```python
@dataclass
class DependencyRecord:
    collection: str      # jetty
    library: str         # gz-physics, the lib whose build declares it
    major: int           # 9
    dependency: str      # dart, the canonical key
    system: str          # deb | brew | conda | bazel | ros
    platform: str        # see below
    declared: str        # as the build wrote it
    version: str | None  # comparable upstream version, None if none resolved
    origin: str          # where the version came from
    label: str | None = None  # shown instead of a missing version
```

| system | platform | declared | origin |
| --- | --- | --- | --- |
| deb | `noble/arm64` | `libdart6.16-dev` | `osrf` or `ubuntu` |
| brew | bottle label of the declaring formula, or `source-only` | `dartsim` | `tap` or `homebrew-core` |
| conda | subdir, `linux-64` | `dartsim-cpp >=6.19.4,<6.20.0a0` | `conda-forge` |
| bazel | `all` | `dartsim 6.13.2.bcr.3` | `bcr` |
| ros | `lyrical@resolute/arm64` | `gz-dartsim-vendor` or `libbullet-dev` | `ros2` or `ubuntu` |

A `(library, major)` shared by several collections (gz-tools 2) produces
records for each of them; the fetches behind them are memoised.

`label` exists for one case: a provider that is found but states no version, a
ROS vendor whose description has none. The record keeps `version=None` and
`label="vendor 0.10.5"`. A declaration nothing resolves has neither and shows as
`?`.

### Versions

`dependency_version(raw)` removes an epoch (`1:`) and a leading `v`, then
returns the leading match of `\d+(\.\d+)*`, or `None` when there is none. That
one rule covers every spelling seen: Debian revisions, `+ds`/`+dfsg`, brew
`~date~sha` and `-date-sha` suffixes, `-rc0`, and `.bcr.N`, whose `.b` ends the
match.

`6.16.6+ds-1~osrf1~noble` -> `6.16.6`; `2.2.6+20211021~312bf40` -> `2.2.6`;
`1.9-20160714-<sha>` -> `1.9`; `3.26.0-rc0.bcr.1` -> `3.26.0`; `v2.3.1` ->
`2.3.1`; `3.24+dfsg-2.1build1` -> `3.24`.

Two versions are equal when their numeric tuples are equal after dropping
trailing zeros, so `1.9` equals `1.9.0`. `series(version)` is the first two
components. The existing `GzVersion` is not reused: it requires exactly three
components.

## The alias table

The only hand-written data in the subsystem. It says which dependencies are
tracked and how each system spells them. Patterns are `re.fullmatch`ed, so
sub-packages such as `libdart6.16-collision-bullet-dev` do not match. ROS
patterns match the name after `ros-<rosdistro>-`; plain Debian names that a ROS
vendor depends on are matched with the `deb` patterns.

```python
DEPENDENCY_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "ogre-next": {
        "deb": (r"libogre-next(-\d+\.\d+)?-dev", r"libogre-2\.\d+-dev"),
        "brew": (r"ogre2\.\d+",),
        "conda": (r"ogre-next",),
        "bazel": (r"ogre-next",),
        "ros": (r"gz-ogre-next-vendor",),
    },
    "ogre": {
        "deb": (r"libogre-1\.\d+-dev",),
        "brew": (r"ogre1\.\d+",),
        "conda": (r"ogre",),
    },
    "dart": {
        "deb": (r"libdart(\d+\.\d+)?-dev",),
        "brew": (r"dartsim(@[\d.]+)?",),
        "conda": (r"dartsim-cpp", r"dartsim"),
        "bazel": (r"dartsim",),
        "ros": (r"gz-dartsim-vendor",),
    },
    "bullet": {
        "deb": (r"libbullet-dev",),
        "brew": (r"bullet(@[\d.]+)?",),
        "conda": (r"bullet-cpp", r"bullet"),
        "bazel": (r"bullet",),
    },
    "zenoh": {
        "deb": (r"libzenohc-dev", r"libzenohcpp-dev"),
        "conda": (r"libzenohc", r"zenoh-cpp"),
        "bazel": (r"zenoh-c", r"zenoh-cpp"),
        "ros": (r"zenoh-cpp-vendor",),
    },
    "mujoco": {
        "deb": (r"libmujoco(-[\d.]+)?-dev",),
        "brew": (r"mujoco",),
        "conda": (r"mujoco",),
        "bazel": (r"mujoco",),
        "ros": (r"mujoco-vendor",),
    },
}

#: Each dependency system follows one library source: it is fetched when that
#: source is, and it applies to a collection when that source does.
DEPENDENCY_SYSTEMS = {
    "deb": "osrf_debian",
    "bazel": "bazel_registry",
    "conda": "conda_forge",
    "brew": "homebrew",
    "ros": "ros_vendor",
}
```

A dependency only gets a row in a collection where some build of that
collection declares it. mujoco has aliases but no live build declares it
(gz-physics has it commented out), so it shows nowhere until one does.

**Alias check.** A reader that sees a declared name matching no alias, where
the name is hosted by Gazebo, adds
`FetchError("deps:aliases", "<collection>/<lib><major> declares <name> (<where>) with no alias")`.
"Hosted by Gazebo" is:

- deb: the binary is in the osrf index and its `Source` is not a gz library;
- brew: `Formula/<name>.rb` exists in the tap and is not a gz formula;
- ros: a `ros-<rosdistro>-*-vendor` whose description is not a gz vendor's.

conda and bazel have no Gazebo-hosted namespace and are not checked. The check
is what keeps the table from going stale without anyone noticing.

## Readers

Every reader is handed the collections, skips a collection for which
`config.source_applies(DEPENDENCY_SYSTEMS[system], collection)` is false, reads
stable channels only, and returns records.

### `deb_control` (system `deb`)

**Declaration.**

1. Candidate release repositories for `(library, major)`: the suffixed prefixes
   of `ground_truth.candidate_tag_prefixes`, with `_` replaced by `-release`
   (`gz-sim6-release`, `ignition-gazebo6-release`, `ign-gazebo6-release`).
2. The repository is the first candidate whose
   `https://raw.githubusercontent.com/gazebo-release/<repo>/main/ubuntu/debian/control`
   exists (`ok_404`). No candidate means no deb declarations for that library.
3. For each live distro (`linux_distros(collections)`), fetch
   `<distro>/debian/control` from that repository with `ok_404`. A distro whose
   file is missing is one this library is not built for.
4. A body that is a single line with no `:` is a relative link. Resolve it
   against the file's directory and fetch again, at most 2 hops, then give up
   with a `FetchError`.
5. If no live distro has a file, `ubuntu/debian/control` applies to the
   collection's declared `distros`.
6. Parse `Build-Depends` of the source stanza: join continuation lines, drop
   `#` comment lines, split on `,`. For each entry, split alternatives on `|`,
   strip `(...)` version constraints and `<...>` build profiles, and honour
   `[...]` architecture qualifiers against amd64 and arm64. Keep the
   alternatives whose name matches a `deb` alias.

**Resolution** per `(distro, arch)`, for an entry with several alternatives the
first that resolves:

- osrf: the newest stanza of that exact binary name in the osrf stable
  `Packages.gz`, the same URL `osrf_debian` fetches;
- Ubuntu: the resolver below;
- the higher `dependency_version` wins and sets `origin`. On a tie the osrf
  record is reported. This compares upstream versions only, a simplification
  of apt's full Debian version comparison.

An entry nothing resolves still yields a record, with `declared` set to its
first matching alternative and `version=None`.

### `deps/ubuntu.py`

`UbuntuResolver(http).resolve(names, distros, arches)` returns
`{(name, distro, arch): raw_version}` from one request:

```
https://people.canonical.com/~ubuntu-archive/madison.cgi
    ?package=<names joined with +>
    &s=<distro>,<distro>-updates,<distro>-security for every distro>
    &a=<arches joined with ,>
    &text=on
```

Each line is `name | version | suite/component | arch, arch`. `noble-updates`
counts as `noble`. The highest `dependency_version` per key is kept. A reader
calls it once per run with the union of its names. A failure raises; the caller
keeps osrf-only resolution for deb and leaves plain debs unresolved for ros,
and adds `FetchError("deps:ubuntu", ...)` saying Ubuntu was not consulted.

### `brew_formula` (system `brew`)

**Declaration.** The formula of `(library, major)` through
`homebrew.formula_names`, the same URLs `homebrew` fetches. Read each
`depends_on "name"` line, skipping any with `=> :build`, `=> :test` or an array
containing either. Keep names matching a `brew` alias.

**Resolution.**

1. The tap's `Formula/<name>.rb` with `ok_404`: the `version "..."` line if
   present, otherwise the version at the end of the `url` (`v2.3.1.tar.gz`,
   `2.87.tar.gz`, or the existing `-X.Y.Z.tar.*` form). Origin `tap`.
2. Otherwise `https://formulae.brew.sh/api/formula/<name>.json`,
   `versions.stable`. Origin `homebrew-core`.
3. Otherwise `version=None`.

**Records.** One per bottle label of the declaring gz formula
(`homebrew.bottle_labels`), or `source-only` when it has none.

### `conda_artifacts` (system `conda`)

**Declaration.**

1. Packages `lib<name>` and `lib<name><major>`, with `CONDA_NAME_OVERRIDES`
   applied to the name, from `https://api.anaconda.org/package/conda-forge/<pkg>`.
   Either may 404; that yields no records, not an error.
2. Per subdir: among the `files[]` of both packages whose version has this
   major and whose `attrs.depends` names at least one `conda` alias, take the
   newest version.
3. Each alias-matching depends spec is a declaration; `declared` is the whole
   spec.

**Resolution.** The floor of the spec (decision 6): the `>=` or `==` bound, or
a bare `X` or `X.*`. No floor gives `version=None`. The HTML detail labels conda
versions "built against".

### `bcr_module` (system `bazel`)

**Declaration.** The newest non-yanked registry version of `(library, major)`,
selected by the function extracted from `BazelRegistrySource`, which also keeps
the registry's raw spelling. Fetch
`https://bcr.bazel.build/modules/<module>/<raw version>/MODULE.bazel` and read
every `bazel_dep(...)` call, multi-line calls included, that is not
`dev_dependency = True` and whose `name` matches a `bazel` alias.

**Resolution.** The pin is exact. `version = dependency_version(pin)`, and
`declared` keeps the pin as written, `-rc0.bcr.1` included.

### `ros_vendor_deps` (system `ros`)

**Ownership.** Walk the `ros2` channel (not `ros2-testing`) for the live distros
and arches through `AptSource`, the same memoised indexes `ros_vendor` reads. A
stanza named `ros-<rosdistro>-*-vendor` whose description parses with
`ros_vendor.parse_description` is a gz vendor of `(library, major)`, which
builds `carried[rosdistro]`. A rosdistro belongs to every collection for which
`carried[rosdistro]` holds at least `COLLECTION_PLATFORM_SHARE` of the
collection's own libraries, except that a `ROLLING_ROSDISTROS` distro belongs only to the newest qualifying
collection. This is the rule `engine.rolling_collection` applies today,
extracted so both use one helper.

**Declaration.** The `Depends` of the gz vendor stanza of each of the
collection's `(library, major)`, split and cleaned as for deb. A
`ros-<rosdistro>-<rest>` entry is matched on `<rest>` against the `ros`
aliases; a plain name against the `deb` aliases.

**Resolution.**

- A dependency vendor: its own stanza in the same index, distro and arch. The
  version is the first `v<digits.digits...>` or `version <digits.digits...>` in
  its description, with origin `ros2`. With no version in the description:
  `version=None`, `label="vendor <upstream part of its Version>"`.
- A plain Debian name: the Ubuntu resolver, with origin `ubuntu`. ROS users do
  not enable the osrf repository, so osrf is not consulted.

## Inventory and marks

`deps/inventory.py` is pure: records in, rows out.

- A **cell** is `(collection, dependency, system)` with its records, the lowest
  and highest version and a `warn` flag.
- A **row** is `(collection, dependency)` with its cells by system and a
  `diverges` flag.
- **⚠ `warn`**: the cell's records carry at least two distinct versions, by the
  equality in [Versions](#versions). That
  covers platforms, declaring libraries and declared names alike. Records
  without a version take no part.
- **◇ `diverges`**: at least two systems in the row have different sets of
  series. Systems with no versioned records take no part. A patch-only
  difference between systems is unmarked.
- **Display.** One version shows as itself; several as `low–high`; no version
  as the records' common label, or `?`.

Marks are computed at render time and never stored.

Expected on the evidence above, and used as tests:

- jetty, ogre-next, deb: `libogre-next-2.3-dev` from osrf is `2.3.1` on noble
  and `2.3.3` on resolute, on both arches, shown as `2.3.1–2.3.3 ⚠`. Ubuntu has
  no package of that name, so it does not take part.
- jetty, dart: deb `6.16.6` (osrf `libdart6.16-dev`, noble and resolute), ros
  lyrical `6.16.6`, conda `6.19.4`, brew `6.19.4`, bazel `6.13.2`. Three
  series, so ◇.
- jetty, ogre: deb and ros `1.9.0` from Ubuntu, brew `1.9` from the tap, conda
  `1.10.12.1`. Series 1.9 against 1.10, so ◇. No cell has ⚠: each system
  agrees with itself.

## Snapshot

`Snapshot.dependencies: list[DependencyRecord] = field(default_factory=list)`.
`to_dict` needs no change.
`from_dict` reads `data.get("dependencies", [])`. The schema stays at 1: a
snapshot written before this change loads with no dependencies, and a tool from
before this change ignores the key.

## Fetch and CLI

- `_collect` runs the readers after the library sources. A reader runs when its
  `DEPENDENCY_SYSTEMS` source is among the selected sources (all of them when
  `--source` is not given), so
  `--source conda_forge` fetches conda libraries and conda dependencies.
  `--collection` narrows both. There is no new fetch flag.
- A reader exception becomes `FetchError("deps:<system>", ...)` and does not
  count toward "every source failed".
- `_filtered` computes the inventory rows from the whole snapshot before
  narrowing, as it already does for statuses, because ◇ compares systems:
  `--source` must not change a mark. Then `--collection` drops rows,
  `--source` drops system columns, and `--lib` keeps records whose declaring
  library is named.
- `--fail-on-problems` never looks at dependencies.

## Rendering

**Console.** Under each collection's library table, a `dependencies` table.

- Rows are the dependencies declared in that collection, sorted by name.
- Columns are the systems, in the registration order of their library sources
  and gated by `config.source_applies` like the library columns. Labels: `deb`, `bazel`, `conda`, `brew`,
  `ros vendor`.
- A cell shows the display text with ⚠ when set, and ◇ is appended to the
  dependency name.
- `--verbose` adds a dependency detail table: platform, declaring library,
  declared, version, origin.
- `--problems-only` prints no dependency tables. The `all` command prints only
  problems to stderr, so no dependency tables there either.
- The legend gains ⚠ and ◇.

**HTML.**

- Each collection section gets a second table below the libraries table, built
  by `build_view` like the first.
- Cells expand into per-platform detail through the existing details markup,
  showing declared, version and origin; conda details say "built against".
- The legend gains ⚠ and ◇.
- After the problems section, a neutral "dependency divergence" section lists
  the ⚠ cells: collection, dependency, system, `low–high`, and the platforms on
  the lowest version. ◇ rows are not listed; the tables show them. Nothing here
  counts as a problem.

## Errors

- A failing reader never stops another reader or any library source.
- A partial failure stays visible rather than quietly wrong: an unreachable
  madison keeps the osrf versions and records `deps:ubuntu`.
- A declaration that resolves nowhere is a record with `version=None`, shown as
  `?`, not an error.
- A control-file link that does not settle within 2 hops is a
  `FetchError("deps:deb", ...)` for that library.
- An unmapped Gazebo-hosted name is a `deps:aliases` error, listed with the
  fetch errors.

## Testing

All offline, driven by the existing `FakeHttpClient`, one fixture per format in
the evidence section.

- `deb_control`: a link-body control file; `a | b` with the second alternative
  resolving; `[!armhf]`; an osrf index holding `libdart6.13-dev` and
  `libdart6.16-dev`; osrf beating Ubuntu and Ubuntu beating osrf; the
  `ubuntu/debian/control` fallback; ignition-era repository naming.
- `ubuntu`: madison text with `-updates` above release; the batched URL.
- `brew_formula`: all three tap version spellings; homebrew-core JSON; a
  `=> :build` dependency skipped; a `source-only` declaring formula.
- `conda_artifacts`: `libgz-physics` with 7.5.0 lacking depends and 9.5.1
  pinned, plus `libgz-physics7`; the floor of `>=`, `==` and `X.*` specs.
- `bcr_module`: a multi-line `bazel_dep`, `dev_dependency = True` skipped,
  `.bcr.N` and `-rc0`.
- `ros_vendor_deps`: rosdistro ownership including Rolling; vendor and plain
  deb Depends; a description with no version giving a label.
- `aliases`: full-match against sub-packages; each kind of alias-check warning.
- `dependency_version` and `series`: a table of the spellings above.
- `inventory`: ⚠ within a system; ◇ on series; a patch-only cross-system
  difference unmarked; unversioned records excluded; the three expected
  outcomes in [Inventory and marks](#inventory-and-marks).
- `snapshot`: round trip, and a snapshot with no `dependencies` key.
- `http`: the same URL is fetched once per client, 404s included.
- `cli` and renderers: the tables and marks appear; `--source` does not change
  a mark; ⚠ never changes the exit code.

## Out of scope

- Comparing a dependency against a required or an upstream version.
- nightly, osrf prerelease and ros2-testing.
- Dependencies of the `ros_gz_debian` (fortress ROS mirror) packages.
- Whether a dependency formula is bottled on the same macOS labels as the gz
  formula.
- Any dependency that is not in the alias table.

## Risks and assumptions

- madison is the archive team's CGI, not a versioned API. Launchpad's
  `getPublishedBinaries` answers the same question (checked for
  `libdart-dev` on noble) and is the fallback if madison goes away.
- The `main` branch and the link-body convention were checked on three
  gazebo-release repositories only; the fixtures pin what was seen.
- deb ties are decided on upstream version only.
- Every conda lib is assumed to follow the `libgz-<x>` output naming; one that
  does not simply contributes no conda records.
- About 170 extra small requests per run, almost all to raw.githubusercontent,
  BCR and anaconda, on top of today's roughly four-minute fetch.
