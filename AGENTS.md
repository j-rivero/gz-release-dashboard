# Design a Gazebo packages dashboard

Goal is to create a code that can parse different sources of Gazebo packages
and display information about the version number in them. Showing all
active Gazebo collections, differnt architectures supported by each packaging
system.

## Sources of packages

* Main source of packages is the packages.osrfoundation.org debian repository
  The URL hosts: stable, prerelease and nightly repos. Stable and prerelease
  are part of this effort, leave nightly out by now.

* Conda-forge packages for gz libraries are also important to cover.

* Brew bottle versions, usually hosted in https://github.com/osrf/homebrew-simulation/

* Bazel central registry versions.

* ROS vendor packages, typically hosted http://packages.ros.org/ros2/ubuntu
  for stable versions or ros-testing for packages waiting for a sync.

## Ground truth for the latest released version

Active collections with each corresponding gazebo libraries are found at:
https://raw.githubusercontent.com/gazebo-tooling/release-tools/refs/heads/master/jenkins-scripts/dsl/gz-collections.yaml

Each of the Gazebo release first push a tag into the github repositories
in the form of ${lib_name}${MAJOR_VERSION}_${full_version} from each supported
branch (from ${lib_name}${MAJOR_VERSION})

i.e: gz-sim https://github.com/gazebosim/gz-sim/tags

## Output

The tool should be able to produce a nice/rich and clear output, using colors
and other emojis or visual artifacts that helps to track where errors in sources
that are behind the latest release.

The outputs needs to cover:

* Linux/Mac console display
* Nice web format ready to be used by github pages

## Considerations

* The metapackages gz-jetty, gz-rolling, etc, should be ignored
* The Rotary collection should be ignored
