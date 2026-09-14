class DartsimAT6100 < Formula
  desc "Dynamic Animation and Robotics Toolkit (openrobotics port)"
  homepage "https://dartsim.github.io/"
  # OSRF's fork
  url "https://github.com/gazebo-forks/dart/archive/d2b6ee08a60d0dbf71b0f008cd8fed1f611f6e24.tar.gz"
  version "6.10.0~20211005~d2b6ee08a60d0dbf71b0f008cd8fed1f611f6e24"
  sha256 "372af181024452418eec95f8a9cd723ceb1ada979208add66c9a4330b9c0fa32"
  license "BSD-2-Clause"
  revision 15

  keg_only "open robotics fork of dart HEAD + custom changes"

  depends_on "cmake" => :build
  depends_on "pkgconf" => :build
  depends_on "assimp"
  depends_on "boost"
  depends_on "bullet"
  depends_on "eigen"
  depends_on "fcl"
  depends_on "flann"
  depends_on "ipopt"
  depends_on "libccd"
  depends_on "nlopt"
  depends_on "ode"
  depends_on "open-scene-graph"
  depends_on "tinyxml2"
  depends_on "urdfdom"
end
