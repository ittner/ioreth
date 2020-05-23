#
# Ioreth - An APRS library and bot
# Copyright (C) 2020  Alexandre Erwin Ittner, PP5ITT <alexandre@ittner.com.br>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


import logging
import subprocess


logging.basicConfig()
logger = logging.getLogger(__name__)


def simple_ping(host, timeout=15):
    """Check if a host is alive by sending a few pings.
    Return True if alive, False otherwise.
    """

    rcode = False
    cmdline = ["ping", "-c", "4", "-W", "3", host]
    proc = subprocess.Popen(cmdline)
    try:
        proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        logger.exception(exc)
    else:
        rcode = proc.returncode == 0
    return rcode


def human_time_interval(secs):
    """Format the number of seconds in summarized, human-friendly, string.
    """
    nsecs = secs
    ndays = int(secs / (24 * 60 * 60))
    nsecs -= ndays * 24 * 60 * 60
    nhours = int(nsecs / (60 * 60))
    nsecs -= nhours * 60 * 60
    nmins = int(nsecs / 60)
    nsecs -= nmins * 60

    if ndays > 0:
        return "%dd %02dh%02dm" % (ndays, nhours, nmins)

    return "%02dh%02dm%02ds" % (nhours, nmins, nsecs)


def get_uptime():
    """Get the system uptime, in seconds.
    Works on Linux, so that's enough.
    """

    with open("/proc/uptime") as fp:
        rdata = fp.read()

    ret_time = None
    if rdata:
        lst = rdata.strip().split()
        if len(lst) > 1:
            ret_time = int(float(lst[0]))

    return ret_time
