class IgnitionRendering6 < Formula
  desc "Rendering library for robotics applications"
  homepage "https://github.com/gazebosim/gz-rendering"
  url "https://osrf-distributions.s3.amazonaws.com/gz-rendering/releases/ignition-rendering-6.6.4.tar.bz2"
  sha256 "f192cf789cb9f45e044511f9ed3a527a81a7f417bb8b1bcb57b32c75bb3ed2af"
  license "Apache-2.0"

  # head "https://github.com/gazebosim/gz-rendering.git", branch: "ign-rendering6"

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 arm64_sequoia: "064f5bf87b47e92f0242076c654b0b862eed0ef6f2f289196d135e08d701d7d2"
    sha256 arm64_sonoma:  "76130cc474c5aacb7cfc58ee502b91f863b00c7812b1d3a1e60e186c523a6c42"
    sha256 sonoma:        "48d618e714a03c476cd6e38da314c36464618fa2c427c2c22940d2f049208289"
  end

  depends_on "cmake" => [:build, :test]
  depends_on "pkgconf" => [:build, :test]

  depends_on "gz-plugin2" => :test

  depends_on "freeimage"
  depends_on "ignition-cmake2"
  depends_on "ignition-common4"
  depends_on "ignition-math6"
  depends_on "ignition-plugin1"
  depends_on "ignition-utils1"
  depends_on "ogre1.9"
  depends_on "ogre2.2"
end
