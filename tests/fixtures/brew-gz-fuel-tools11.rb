class GzFuelTools11 < Formula
  desc "Classes and tools for interacting with Gazebo Fuel"
  homepage "https://github.com/gazebosim/gz-fuel-tools"
  url "https://osrf-distributions.s3.amazonaws.com/gz-fuel-tools/releases/gz-fuel_tools-11.0.0.tar.bz2"
  sha256 "aaaa"
  license "Apache-2.0"
  revision 34

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 cellar: :any, arm64_sequoia: "bbbb"
    sha256 cellar: :any, arm64_sonoma:  "cccc"
    sha256 cellar: :any, sonoma:        "dddd"
  end
end
