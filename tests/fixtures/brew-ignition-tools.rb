class IgnitionTools < Formula
  desc "Ignition tools"
  homepage "https://github.com/gazebosim/gz-tools"
  url "https://osrf-distributions.s3.amazonaws.com/ign-tools/releases/ignition-tools-1.5.0.tar.bz2"
  sha256 "eeee"
  license "Apache-2.0"
  revision 1

  bottle do
    sha256 cellar: :any_skip_relocation, arm64_sonoma: "ffff"
    sha256 cellar: :any_skip_relocation, ventura:      "gggg"
  end
end
