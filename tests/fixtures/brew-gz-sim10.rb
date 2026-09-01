class GzSim10 < Formula
  desc "Gazebo Sim robot simulator"
  homepage "https://github.com/gazebosim/gz-sim"
  url "https://osrf-distributions.s3.amazonaws.com/gz-sim/releases/gz-sim-10.5.0.tar.bz2"
  sha256 "2f609f8130ee3e9ce9de0e8e94aa9aa92f0eb433ac256c84f38932f988edd4f0"
  license "Apache-2.0"
  revision 10

  head "https://github.com/gazebosim/gz-sim.git", branch: "gz-sim10"

  bottle do
    root_url "https://osrf-distributions.s3.amazonaws.com/bottles-simulation"
    sha256 arm64_sequoia: "10a372dc77e1010ee80a36d5a770aa968d33c10ea59eb116e79d5356368e54b1"
    sha256 arm64_sonoma:  "b152984e1babb55de5aa30259472100525c05fbb6ccdebd00bd9900f803d0479"
    sha256 sonoma:        "684e8967c31a61b5e358a7780c7be4a6e88340c0bfeadce5e8c5a338d85ba296"
  end

  depends_on "gz-cmake5"

  test do
    system "true"
  end
end
