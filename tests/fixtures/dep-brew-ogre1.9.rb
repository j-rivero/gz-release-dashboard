class Ogre19 < Formula
  desc "Scene-oriented 3D engine written in c++"
  homepage "https://ogrecave.github.io/ogre/"
  url "https://osrf-distributions.s3.amazonaws.com/ogre/releases/sinbad-ogre-108ab0bcc696.tar.bz2"
  version "1.9-20160714-108ab0bcc69603dba32c0ffd4bbbc39051f421c9"
  sha256 "3ca667b959905b290d782d7f0808e35d075c85db809d3239018e4e10e89b1721"
  license "MIT"
  revision 11

  # head "https://github.com/OGRECave/ogre.git", branch: "master"

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 cellar: :any, arm64_sequoia: "3282b179037373e883c126734000e087cfbe62af24eee0536274a454a564dd8d"
    sha256 cellar: :any, arm64_sonoma:  "e248599295052303f3752d01ea0ae4edb6307a49ad6ef6b21143729b33d1cb6f"
    sha256 cellar: :any, sonoma:        "8eb999e92b356251d6a5676089a0656a8556cf9c92e817c5d95f7bb9185e1696"
    sha256 cellar: :any, ventura:       "87c237e4b2428721d62b74e74273942d037646015851ff3e5dd7c671102eeeac"
  end

  option "with-cg"

  depends_on "cmake" => :build
  depends_on "boost"
  depends_on "doxygen"
  depends_on "freeimage"
  depends_on "freetype"
  depends_on "libx11"
  depends_on "libzzip"
  depends_on "tbb"
end
