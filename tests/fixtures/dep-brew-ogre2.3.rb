class Ogre23 < Formula
  desc "Scene-oriented 3D engine written in c++"
  homepage "https://www.ogre3d.org/"
  url "https://github.com/OGRECave/ogre-next/archive/refs/tags/v2.3.1.tar.gz"
  sha256 "38dd0d5ba5759ee47c71552c5dacf44dad5fe61868025dcbd5ea6a6bdb6bc8e4"
  license "MIT"
  revision 2

  # head "https://github.com/OGRECave/ogre-next.git", branch: "v2-3"

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 cellar: :any, arm64_sequoia: "9e3d6499d30d18d1fb74fc6d4267dd6448ce34d3bb567f5a7b19471bf235cd8c"
    sha256 cellar: :any, arm64_sonoma:  "be121e86ff8d7def125d8579583fbf32b9bcd475f2b2eee7f20948aa4afc6aee"
    sha256 cellar: :any, sonoma:        "00e8a7721f3a33eb5f5df26c70a597e71ee06328949cecae7e85c79badf8a34f"
    sha256 cellar: :any, ventura:       "a99ca4c5adc6c3455d9df29aa00c944f3dddb2ff64c176cb37efc759b8bc1498"
    sha256 cellar: :any, monterey:      "58e4f7a6d4e1ae1a70b2f449801b4335deb378dc982f38f2bc3cfc6393a5e0b0"
    sha256 cellar: :any, big_sur:       "2cd52cc99ea96660c7a83e2c5458c900f0abd4af3fdd7b69117ad87b407d0a2a"
  end

  depends_on "cmake" => :build
  depends_on "gz-plugin2" => :test
  depends_on "pkgconf" => :test

  depends_on "doxygen"
  depends_on "freeimage"
  depends_on "freetype"
  depends_on "libx11"
  depends_on "libzzip"
  depends_on "rapidjson"
  depends_on "tbb"

  conflicts_with "gz-rotary-ogre2.3-vendor", because: "both install ogre2.3"
end
