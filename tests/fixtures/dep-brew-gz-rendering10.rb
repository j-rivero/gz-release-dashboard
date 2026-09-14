class GzRendering10 < Formula
  desc "Rendering library for robotics applications"
  homepage "https://gazebosim.org"
  url "https://osrf-distributions.s3.amazonaws.com/gz-rendering/releases/gz-rendering-10.0.2.tar.bz2"
  sha256 "6a4b71dad22a758494570b6e76344744106934ba56f5e58ad3f6bb9e7efb60e2"
  license "Apache-2.0"

  head "https://github.com/gazebosim/gz-rendering.git", branch: "gz-rendering10"

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 arm64_sequoia: "2bbce7da56001c626b463f66d2934465949e4721093655ee384c717c63122186"
    sha256 arm64_sonoma:  "67f8ee64e75b9899e7c0b2100cae147f17860ddf414fecb56f12417f3cb2d18c"
    sha256 sonoma:        "adbb4f4bfc52569a80cd89992d907fba2ca670d25ac4380451fcd7e8ab515036"
  end

  depends_on "cmake" => [:build, :test]
  depends_on "pkgconf" => [:build, :test]

  depends_on "fmt"
  depends_on "freeimage"
  depends_on "gz-cmake5"
  depends_on "gz-common7"
  depends_on "gz-math9"
  depends_on "gz-plugin4"
  depends_on "gz-utils4"
  depends_on "ogre1.9"
  depends_on "ogre2.3"
  depends_on "spdlog"

  conflicts_with "gz-rotary-rendering", because: "both install gz-rendering"
end
