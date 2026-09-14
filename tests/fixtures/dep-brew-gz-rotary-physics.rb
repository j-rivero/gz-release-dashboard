class GzRotaryPhysics < Formula
  desc "Physics library for robotics applications"
  homepage "https://github.com/gazebosim/gz-physics"
  license "Apache-2.0"

  head "https://github.com/gazebosim/gz-physics.git", branch: "main"

  depends_on "cmake" => [:build, :test]

  depends_on "assimp"
  depends_on "bullet"
  depends_on "dartsim"
  depends_on "fcl"
  depends_on "fmt"
  depends_on "google-benchmark"
  depends_on "gz-rotary-cmake"
  depends_on "gz-rotary-common"
  depends_on "gz-rotary-math"
  depends_on "gz-rotary-plugin"
  depends_on "gz-rotary-sdformat"
  depends_on "gz-rotary-utils"
  depends_on "libccd"
  depends_on "octomap"
  depends_on "ode"
  depends_on "pkgconf"
  depends_on "spdlog"
  depends_on "tinyxml2"
  depends_on "urdfdom"

  conflicts_with "gz-jetty-physics", because: "both install gz-physics"
end
