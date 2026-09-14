class GzPhysics9 < Formula
  desc "Physics library for robotics applications"
  homepage "https://github.com/gazebosim/gz-physics"
  url "https://osrf-distributions.s3.amazonaws.com/gz-physics/releases/gz-physics-9.5.1.tar.bz2"
  sha256 "e005e57c582174bdc3d8dd0e6a064365a9006b9cd1483c980c4c70b8c704b48a"
  license "Apache-2.0"

  head "https://github.com/gazebosim/gz-physics.git", branch: "gz-physics9"

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 arm64_sequoia: "18bff09423d66cc8b5b39a99cebd4a296a0c3fb45aa8458115b29d8dd5e73ae6"
    sha256 arm64_sonoma:  "ddc7f0a201268b0128a9f2a9e2cb417cd9e847f5c0f381f96f412a55be92bbb1"
  end

  depends_on "cmake" => [:build, :test]

  depends_on "assimp"
  depends_on "bullet"
  depends_on "dartsim"
  depends_on "fcl"
  depends_on "fmt"
  depends_on "google-benchmark"
  depends_on "gz-cmake5"
  depends_on "gz-common7"
  depends_on "gz-math9"
  depends_on "gz-plugin4"
  depends_on "gz-utils4"
  depends_on "libccd"
  depends_on "octomap"
  depends_on "ode"
  depends_on "pkgconf"
  depends_on "sdformat16"
  depends_on "spdlog"
  depends_on "tinyxml2"
  depends_on "urdfdom"

  conflicts_with "gz-rotary-physics", because: "both install gz-physics"
end
