class Sdformat9 < Formula
  desc "Simulation Description Format"
  homepage "http://sdformat.org"
  url "https://osrf-distributions.s3.amazonaws.com/sdformat/releases/sdformat-9.10.1.tar.bz2"
  sha256 "0b6af9955a94a22b077eb915f2b61b35f55963c12d0f1aecb5fbe5b51347a50d"
  license "Apache-2.0"
  revision 1

  head "https://github.com/gazebosim/sdformat.git", branch: "sdf9"

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 sonoma:   "b7a50cebce58dc261605949c8b796739036876f3c185e2d225309d60c9c7acf8"
    sha256 ventura:  "ac0f11dbdb6bfd75df7aa11b13d014bb2624febd625de524625f250198baa0b4"
    sha256 monterey: "0d72b95fa548878ccb2272c1bf793e65a274af39ce0de5fb41c4b8a5a647b50d"
  end

  deprecate! date: "2025-01-31", because: "is past end-of-life date"

  depends_on "cmake" => [:build, :test]
  depends_on "pkgconf" => [:build, :test]

  depends_on "doxygen"
  depends_on "ignition-math6"
  depends_on "ignition-tools"
  depends_on "tinyxml1"
  depends_on "urdfdom"
end
