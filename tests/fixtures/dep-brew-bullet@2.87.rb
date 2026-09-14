class BulletAT287 < Formula
  desc "Physics SDK"
  homepage "https://bulletphysics.org/"
  url "https://github.com/bulletphysics/bullet3/archive/refs/tags/2.87.tar.gz"
  sha256 "438c151c48840fe3f902ec260d9496f8beb26dba4b17769a4a53212903935f95"
  license "Zlib"
  head "https://github.com/bulletphysics/bullet3.git"

  option "with-framework", "Build frameworks"
  option "with-demo", "Build demo applications"
  option "with-double-precision", "Use double precision"

  deprecated_option "framework" => "with-framework"
  deprecated_option "build-demo" => "with-demo"
  deprecated_option "double-precision" => "with-double-precision"

  deprecate! date: "2025-09-30", because: "not used by supported package"

  depends_on "cmake" => :build
end
