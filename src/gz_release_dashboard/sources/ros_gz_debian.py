"""The gz packages as ROS ships them: repos.ros.org and packages.ros.org.

Not vendor packages -- those are :mod:`~gz_release_dashboard.sources.ros_vendor`
-- but the very same source packages packages.osrfoundation.org builds,
imported into the two Debian repositories the ROS world installs from. So this
is nothing but a pair of repository URLs read by the shared
:class:`~gz_release_dashboard.sources.debian_repo.GzAptSource`.
"""

from __future__ import annotations

from .. import config
from . import register_source
from .debian_repo import GzAptSource


@register_source
class RosGzDebianSource(GzAptSource):
    """One record per (channel, distro, arch, library), exactly as for osrf deb.

    ``bootstrap`` is what the ROS buildfarm builds against and ``stable`` is
    what a ROS user apt-gets, so a Gazebo release has only really reached ROS
    once both agree with packages.osrfoundation.org. Being behind in either is
    a real gap and is reported as one; neither is a staging channel.

    Which distributions get asked for takes care of itself: the import only
    exists for the ignition generation, so jammy is the only Linux release that
    answers with anything, and the collections that never went through it have
    no cells here at all.
    """

    name = "ros_gz_debian"
    channels = ("bootstrap", "stable")
    repositories = config.ROS_GZ_DEB_CHANNELS
    arches = config.ROS_DEB_ARCHES
    fallback_distros = config.ROS_DEB_DISTROS
