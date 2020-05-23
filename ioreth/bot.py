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

import sys
import time
import logging
import configparser
import os
import re

logging.basicConfig()
logger = logging.getLogger(__name__)

from .clients import AprsClient
from . import aprs
from . import remotecmd
from . import utils


def is_br_callsign(callsign):
    return bool(re.match("P[PTUY][0-9].+", callsign.upper()))


class BotAprsHandler(aprs.Handler):
    def __init__(self, callsign, client):
        aprs.Handler.__init__(self, callsign)
        self._client = client

    def on_aprs_message(self, source, addressee, text, msgid=None, via=None):
        """Handle an APRS message.

        This may be a directed message, a bulletin, announce ... with or
        without confirmation request, or maybe just trash. We will need to
        look inside to know.
        """

        if addressee.strip().upper() != self.callsign.upper():
            # This message was not sent for us.
            return

        self.handle_aprs_msg_bot_query(source, text)
        if msgid:
            # APRS Protocol Reference 1.0.1 chapter 14 (page 72) says we can
            # reject a message by sending a rejXXXXX instead of an ackXXXXX
            # "If a station is unable to accept a message". Not sure if it is
            # semantically correct to use this for an invalid query for a bot,
            # so always acks.
            logger.info("Sending ack to message %s from %s.", msgid, source)
            self.send_aprs_msg(source, "ack" + msgid)

    def handle_aprs_msg_bot_query(self, source, text):
        """We got an text message direct to us. Handle it as a bot query.
        TODO: Make this a generic thing.

        source: the sender's callsign+SSID
        text: message text.
        """

        qry_args = text.lstrip().split(" ", 1)
        qry = qry_args[0].lower()
        args = ""
        if len(qry_args) == 2:
            args = qry_args[1]

        random_replies = {
            "moria": "Pedo mellon a minno",
            "mellon": "*door opens*",
            "mellon!": "**door opens**  🚶🚶🚶🚶🚶🚶🚶🚶🚶  💍→🌋",
            "meow": "=^.^=  purr purr  =^.^=",
            "clacks": "GNU Terry Pratchett",
            "73": "73 🖖",
        }

        if qry == "ping":
            self.send_aprs_msg(source, "Pong! " + args)
        elif qry == "version":
            self.send_aprs_msg(source, "Python " + sys.version.replace("\n", " "))
        elif qry == "time":
            self.send_aprs_msg(
                source, "Localtime is " + time.strftime("%Y-%m-%d %H:%M:%S UTC%Z")
            )
        elif qry == "help":
            self.send_aprs_msg(source, "Valid commands: ping, version, time, help")
        elif qry in random_replies:
            self.send_aprs_msg(source, random_replies[qry])
        else:
            if is_br_callsign(source):
                self.send_aprs_msg(
                    source, "Sou um bot. Envie 'help' para a lista de comandos"
                )
            else:
                self.send_aprs_msg(source, "I'm a bot. Send 'help' for command list")

    def send_aprs_msg(self, to_call, text):
        self._client.enqueue_frame(self.make_aprs_msg(to_call, text))

    def send_aprs_status(self, status):
        self._client.enqueue_frame(self.make_aprs_status(status))


class SystemStatusCommand(remotecmd.BaseRemoteCommand):
    def __init__(self, cfg):
        remotecmd.BaseRemoteCommand.__init__(self, "system-status")
        self._cfg = cfg
        self.status_str = ""

    def run(self):
        net_status = (
            self._check_host_scope("Eth", "eth_host")
            + self._check_host_scope("Inet", "inet_host")
            + self._check_host_scope("DNS", "dns_host")
            + self._check_host_scope("VPN", "vpn_host")
        )
        self.status_str = "At %s: Uptime %s" % (
            time.strftime("%Y-%m-%d %H:%M:%S UTC%Z"),
            utils.human_time_interval(utils.get_uptime()),
        )
        if len(net_status) > 0:
            self.status_str += "," + net_status

    def _check_host_scope(self, name, cfg_key):
        if not cfg_key in self._cfg:
            return ""
        ret = utils.simple_ping(self._cfg[cfg_key])
        if ret:
            return " " + name + ":Ok"
        return " " + name + ":Err"


class ReplyBot(AprsClient):
    def __init__(self, config_file):
        AprsClient.__init__(self)
        self._aprs = BotAprsHandler("", self)
        self._config_file = config_file
        self._config_mtime = None
        self._cfg = configparser.ConfigParser()
        self._check_updated_config()
        self._last_blns = time.monotonic()
        self._last_status = time.monotonic()
        self._rem = remotecmd.RemoteCommandHandler()

    def _load_config(self):
        try:
            self._cfg.clear()
            self._cfg.read(self._config_file)
            self.addr = self._cfg["tnc"]["addr"]
            self.port = int(self._cfg["tnc"]["port"])
            self._aprs.callsign = self._cfg["aprs"]["callsign"]
            self._aprs.path = self._cfg["aprs"]["path"]
        except Exception as exc:
            logger.error(exc)

    def _check_updated_config(self):
        try:
            mtime = os.stat(self._config_file).st_mtime
            if self._config_mtime != mtime:
                self._load_config()
                self._config_mtime = mtime
                logger.info("Configuration reloaded")
        except Exception as exc:
            logger.error(exc)

    def on_connect(self):
        logger.info("Connected")

    def on_disconnect(self):
        logger.warning("Disconnected! Connecting again...")
        self.connect()

    def on_recv_frame(self, frame):
        self._aprs.handle_frame(frame)

    def _update_bulletins(self):
        if not self._cfg.has_section("bulletins"):
            return

        max_age = self._cfg.getint("bulletins", "send_freq", fallback=600)
        now_mono = time.monotonic()
        if now_mono < (self._last_blns + max_age):
            return

        self._last_blns = now_mono
        logger.info("Bulletins are due for update (every %s seconds)", max_age)

        # Bulletins have names in format BLNx, we should send them in
        # alfabetical order.
        blns_to_send = []
        keys = self._cfg.options("bulletins")
        keys.sort()
        for key in keys:
            bname = key.upper()
            if len(bname) == 4 and bname.startswith("BLN"):
                blns_to_send.append((bname, self._cfg.get("bulletins", key)))

        # TODO: any post-processing here?
        for (bln, text) in blns_to_send:
            self._aprs.send_aprs_msg(bln, text)

    def _update_status(self):
        if not self._cfg.has_section("status"):
            return

        max_age = self._cfg.getint("status", "send_freq", fallback=600)
        now_mono = time.monotonic()
        if now_mono < (self._last_status + max_age):
            return

        self._last_status = now_mono
        self._rem.post_cmd(SystemStatusCommand(self._cfg["status"]))

    def on_loop_hook(self):
        AprsClient.on_loop_hook(self)
        self._check_updated_config()
        self._update_bulletins()
        self._update_status()

        # Poll results from external commands, if any.
        while True:
            rcmd = self._rem.poll_ret()
            if not rcmd:
                break
            self.on_remote_command_result(rcmd)

    def on_remote_command_result(self, cmd):
        logger.debug("ret = %s", cmd)

        if isinstance(cmd, SystemStatusCommand):
            self._aprs.send_aprs_status(cmd.status_str)
