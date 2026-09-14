class Ogre22 < Formula
  desc "Scene-oriented 3D engine written in c++"
  homepage "https://www.ogre3d.org/"
  url "https://github.com/OGRECave/ogre-next/archive/312bf406a77244afe230930e67e3e5d52a119507.tar.gz"
  version "2.2.6+20211021~312bf40"
  sha256 "b9dbd84ef0c1731d0d1abc55499532358b9a9e5f0b3dc2b8e02ba76db0a112fd"
  license "MIT"
  revision 2

  # head "https://github.com/OGRECave/ogre-next.git", branch: "v2-2"

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 cellar: :any, arm64_sequoia: "2b5e3a71c96ceb7cfb5c1e51ef92789b63899f27ed573cf35e693b365c2082ee"
    sha256 cellar: :any, arm64_sonoma:  "e4aff5408f38e2ddbdda3b582f3d445de431e8723640c688574a4fe692e7f7c3"
    sha256 cellar: :any, sonoma:        "69e1b4dcd9ab083f9328a82930e544621b19afffa4101f4447ac2fc7da1ac2df"
    sha256 cellar: :any, ventura:       "39ee442113fbe0e76dd71f6cd9b90fb3cbb16de3a771c32d6fe12a0a4679dbdc"
    sha256 cellar: :any, monterey:      "0bd7b3f41e27834ff7ac6ae7c0711e18cb64bb0d1795903e98335e8618e3eb22"
    sha256 cellar: :any, big_sur:       "7d348ad79b4dc945b7305523d0826bb42d42747c921433fe792f4fe68d2e5191"
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
end
