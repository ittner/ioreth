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
#
# ========
#
# This fork of Ioreth was modified by Angelo 4I1RAC/N2RAC to support additional
# functionalities, such as a means to store callsigns from a "net" checkin
# as well as a means to forward messages to all stations checked in for the day
# It is also supported by local cron jobs on my own machine and web server
# to publish the net log on a regular basis.
# 
# Pardon my code. My knowledge is very rudimentary, and I only modify or create
# functions as I need them. If anyone can help improve on the code and the
# logic of this script, I would very much appreciate it.
# You may reach me at qsl@n2rac.com or simply APRS message me at N2RAC-7.
#
# A lot of the items here are still poorly documented if at all. Many also
# rely on some weird or nuanced scripts or directory structures that I have
# maintained on my own machine or server, so bear with me.
# The non-indented comments are mine. The indented ones are by Alexandre.
# A lot of this is trial-and-error for me, so again, please bear with me.
#
#


import sys
import time
import logging
import configparser
import os
import re
import random

logging.basicConfig()
logger = logging.getLogger(__name__)

from cronex import CronExpression
from .clients import AprsClient
from . import aprs
from . import remotecmd
from . import utils
from os import path

# These lines below I have added in order to provide a means for ioreth to store
# and retrieve a list of "net" checkins on a daily basis. I did not bother to use
# more intuitive names for the files, but I can perhaps do so in a later code cleanup.
# Note that the paths are full. You may wish to include these settings in the config file
# as part of code cleanup.
# Also, note that "filename2" is the file that gets published to the web via cron job.
# It is a cumulative list of checkins, which includes timestamp, callsign+ssid, and messege.

timestr = time.strftime("%Y%m%d")
filename1 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr
filename2 = "home/pi/ioreth/ioreth/ioreth/netlog-msg"
filename3 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr+"-cr"
dusubs = "/home/pi/ioreth/ioreth/ioreth/dusubs"
dusubslist = "/home/pi/ioreth/ioreth/ioreth/dusubslist"
file = open(filename1, 'a')
file = open(filename3, 'a')

# Also Mmoved time string to place where it can be reset at midnight

def is_br_callsign(callsign):
    return bool(re.match("P[PTUY][0-9].+", callsign.upper()))


class BotAprsHandler(aprs.Handler):
    def __init__(self, callsign, client):
        aprs.Handler.__init__(self, callsign)
        self._client = client

    def on_aprs_message(self, source, addressee, text, origframe, msgid=None, via=None):
        """Handle an APRS message.

        This may be a directed message, a bulletin, announce ... with or
        without confirmation request, or maybe just trash. We will need to
        look inside to know.
        """

        if addressee.strip().upper() != self.callsign.upper():
            # This message was not sent for us.
            return

        if re.match(r"^(ack|rej)\d+", text):
            # We don't ask for acks, but may receive them anyway. Spec says
            # acks and rejs must be exactly "ackXXXX" and "rejXXXX", case
            # sensitive, no spaces. Be a little conservative here and do
            # not try to interpret anything else as control messages.
            logger.info("Ignoring control message %s from %s", text, source)
            return

        self.handle_aprs_msg_bot_query(source, text, origframe)
        if msgid:
            # APRS Protocol Reference 1.0.1 chapter 14 (page 72) says we can
            # reject a message by sending a rejXXXXX instead of an ackXXXXX
            # "If a station is unable to accept a message". Not sure if it is
            # semantically correct to use this for an invalid query for a bot,
            # so always acks.
            logger.info("Sending ack to message %s from %s.", msgid, source)
            self.send_aprs_msg(source.replace('*',''), "ack" + msgid)



    def handle_aprs_msg_bot_query(self, source, text, origframe):
        """We got an text message direct to us. Handle it as a bot query.
        TODO: Make this a generic thing.

        source: the sender's callsign+SSID
        text: message text.
        """

        sourcetrunc = source.replace('*','')
        qry_args = text.lstrip().split(" ", 1)
        qry = qry_args[0].lower()
        args = ""

# Assign a message ID. We need a more elegant solution than this one. Right now, it
# Just uses a number based on the current minute. Not very nice, but it works.

        mesgid = time.strftime("%u%M")
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
            self.send_aprs_msg(source, "Pong! " + args + "{" + mesgid)
        elif qry == "?aprst" or qry == "?ping?":
            tmp_lst = (
                origframe.to_aprs_string()
                .decode("utf-8", errors="replace")
                .split("::", 2)
            )
            self.send_aprs_msg(source, tmp_lst[0] + ":")
        elif qry == "version":
            self.send_aprs_msg(source, "Python " + sys.version.replace("\n", " ") + " {" + mesgid)
        elif qry == "time":
            mesgid = time.strftime("%S")
            self.send_aprs_msg(
                source, "Localtime is " + time.strftime("%Y-%m-%d %H:%M:%S %Z") + " {" + mesgid
            )
        elif qry == "help":
            self.send_aprs_msg(sourcetrunc, "Valid cmds: NET+mesg,LOG,CQ+mesg,PING,?APRST,VERSION,TIME,HELP" + " {" + mesgid)

# This logs a user's callsign into a temporary file called "netlog" which can be processed later on.
# It also logs the inclued message into a cumulative list which can then be published somewhere.
            
        elif qry == "net":
           sourcetrunc = source.replace('*','')
           with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as g:
                data3 = "{} {}: {}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
                g.write(data3)
                logger.info("Writing %s net message to netlog-msg", sourcetrunc)
           file = open(filename1, 'r')
           search_word = sourcetrunc

            
# This portion below checks if the callsign+ssid has been logged already. If it is, the callsign+ssid
# is no longer processed so that there will be no duplications in the list (which can be unruly for APRS
# messaging if too long. The message is still recorded in netlog-msg for publishing, though.

            if(search_word in file.read()):
              self.send_aprs_msg(sourcetrunc, "Alrdy in log. QSL addnl msg. CQ+mesg,LOG,HELP for more cmds" + " {" + mesgid)
              logger.info("Checked if %s already logged to prevent duplicate", sourcetrunc)
           else:
                with open('/home/pi/ioreth/ioreth/ioreth/netlog', 'w') as f:
                      f.write(sourcetrunc)
                      logger.info("Writing %s checkin to netlog", source)
                self.send_aprs_msg(sourcetrunc, "QSL " + sourcetrunc + ". U may msg all QRX by sending 'CQ' + text." + " {" + mesgid)
                self.send_aprs_msg(sourcetrunc, "Msg 'Log' fr list. Pls QRX for CQ msgs. aprs.dx1arm.net for info. {199")
                logger.info("Replying to %s checkin message", sourcetrunc)
                if os.path.isfile(filename1):
                      file = open(filename1, 'r')
                      data2 = file.read()  
                      file.close()

# This portion below returns a list of checkins for the day.  
# WISHLIST/TODO: Find a way to split the message if it is too long for the 67-character APRS message limit.
                        
        elif qry == "log":
           if os.path.isfile(filename1):
                 file = open(filename1, 'r')
                 data2 = file.read()  
                 file.close()
                 self.send_aprs_msg(source, timestr + ": " + data2 + "{" + mesgid)
                 self.send_aprs_msg(source, "Send 'CQ'+text to msg all in today's log. Info: aprs.dx1arm.net {297")
                 logger.info("Replying with stations heard today: %s", data2)


           else:
                 self.send_aprs_msg(source, "No stations have checked in yet. Send 'net' to checkin." + " {" + mesgid) 

# CQ forwards message to all stations in the day's log. It retrieves the list of recipients from the day's
# line-separated list, and parses these as the destination for the message. The "replace" function is due to the 
# extra line space that is somehow added into each callsign, which previously caused malformed frames.

        elif qry == "cq":
           sourcetrunc = source.replace('*','')
           if os.path.isfile(filename3):
             lines = []
             with open(filename3) as f:
                  lines = f.readlines()
             count = 0
             for line in lines:
                  count += 1
                  self.send_aprs_msg(f'{line}'.replace('\n',''), sourcetrunc + "/" + args + " {" + mesgid)
                  self.send_aprs_msg(f'{line}'.replace('\n',''), "Reply 'CQ'+text to send all on today's list. 'Log' to view." + " {398")
                  logger.info("Sending CQ message to %s", line)
#                  time.sleep(10)
# Wanted to add a time delay of XX seconds per station to prevent packet storms but apparently this is not the right place.
# Apparently, I am trying the wrong place.

# This reads the day's log from a line-separated list for processing one message at a time.

             file = open(filename1, 'r')
             data2 = file.read()  
             file.close()
             self.send_aprs_msg(source, "QSP " + data2 + "{373")
             logger.info("Advising %s of messages sent to %s", sourcetrunc, data2)

           else:
                  self.send_aprs_msg(sourcetrunc, "No stations have checked in yet. Send 'net' to checkin." + " {" + mesgid) 
                  logger.info("Sending CQ message to %s", line)

# This is for a certain list of permanent subscribers, which I have named DU. It's intended for emergency/tactical purposes only,
# which includes stations in my nearby vicinity. In essence, it acts like "CQ" but the list is not refereshed every day.
# I intend to copy this functionality to a group list that can be subscribed to like NET but does not expire every midnight.

        elif qry == "du":
             sourcetrunc = source.replace('*','')
             lines = []
             with open(dusubs) as f:
                  lines = f.readlines()
             count = 0
             for line in lines:
                  count += 1
                  self.send_aprs_msg(f'{line}'.replace('\n',''), sourcetrunc + "/" + args + " {" + mesgid)
                  logger.info("Sending DU message to %s", line)
             file = open(dusubslist, 'r')
             data2 = file.read()  
             file.close()
             self.send_aprs_msg(source, "Sent msg to " + count + " recipients. Ask N2RAC for list." + " {" + mesgid)
             logger.info("Advising %s of messages sent to %s", sourcetrunc, data2)

        elif qry in random_replies:
            self.send_aprs_msg(source, random_replies[qry]  + "{" + mesgid)
        else:
            if is_br_callsign(source):
                self.send_aprs_msg(
                    source, "Sou um bot. Envie 'help' para a lista de comandos"
                )
            else:
                self.send_aprs_msg(source, "'Net'+text to checkin,'Log' for QRX list,'Help' for cmds." + " {" + mesgid)



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
            time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            utils.human_time_interval(utils.get_uptime()),
        )
        if len(net_status) > 0:
            self.status_str += "," + net_status

    def _check_host_scope(self, label, cfg_key):
        if not cfg_key in self._cfg:
            return ""
        ret = utils.simple_ping(self._cfg[cfg_key])
        return " " + label + (":Ok" if ret else ":Err")


class ReplyBot(AprsClient):
    def __init__(self, config_file):
        AprsClient.__init__(self)
        self._aprs = BotAprsHandler("", self)
        self._config_file = config_file
        self._config_mtime = None
        self._cfg = configparser.ConfigParser()
        self._cfg.optionxform = str  # config is case-sensitive
        self._check_updated_config()
        self._last_blns = time.monotonic()
        self._last_cron_blns = 0
        self._last_status = time.monotonic()
        self._last_reconnect_attempt = 0
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
        logger.warning("Disconnected! Will try again soon...")

    def on_recv_frame(self, frame):
        self._aprs.handle_frame(frame)
    def _update_bulletins(self):
        if not self._cfg.has_section("bulletins"):
            return

        max_age = self._cfg.getint("bulletins", "send_freq", fallback=600)

        # There are two different time bases here: simple bulletins are based
        # on intervals, so we can use monotonic timers to prevent any crazy
        # behavior if the clock is adjusted and start them at arbitrary moments
        # so we don't need to worry about transmissions being concentrated at
        # some magic moments. Rule-based blns are based on wall-clock time, so
        # we must ensure they are checked exactly once a minute, behaves
        # correctly when the clock is adjusted, and distribute the transmission
        # times to prevent packet storms at the start of minute.

        now_mono = time.monotonic()
        now_time = time.time()

        # Optimization: return ASAP if nothing to do.
        if (now_mono <= (self._last_blns + max_age)) and (
            now_time <= (self._last_cron_blns + 60)
        ):
            return

        bln_map = dict()

        # Find all standard (non rule-based) bulletins.
        keys = self._cfg.options("bulletins")
        keys.sort()
        std_blns = [
            k for k in keys if k.startswith("BLN") and len(k) > 3 and "_" not in k
        ]

        # Do not run if time was not set yet (e.g. Raspberry Pis getting their
        # time from NTP but before conecting to the network)
        time_was_set = time.gmtime().tm_year > 2000

        # Map all matching rule-based bulletins.
        if time_was_set and now_time > (self._last_cron_blns + 60):
            # Randomize the delay until next check to prevent packet storms
            # in the first seconds following a minute. It will, of course,
            # still run within the minute.
            timestr = time.strftime("%Y%m%d")
            filename1 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr

            self._last_cron_blns = 60 * int(now_time / 60.0) + random.randint(0, 30)

            cur_time = time.localtime()
            utc_offset = cur_time.tm_gmtoff / 3600  # UTC offset in hours
            ref_time = cur_time[:5]  # (Y, M, D, hour, min)

            for k in keys:
                # if key is "BLNx_rule_x", etc.
                lst = k.split("_", 3)
                if (
                    len(lst) == 3
                    and lst[0].startswith("BLN")
                    and lst[1] == "rule"
                    and (lst[0] not in std_blns)
                ):
                    expr = CronExpression(self._cfg.get("bulletins", k))
                    if expr.check_trigger(ref_time, utc_offset):
                        bln_map[lst[0]] = expr.comment

        # If we need to send standard bulletins now, copy them to the map.
        if now_mono > (self._last_blns + max_age):
            self._last_blns = now_mono
            for k in std_blns:
                bln_map[k] = self._cfg.get("bulletins", k)

        if len(bln_map) > 0:
            to_send = [(k, v) for k, v in bln_map.items()]
            to_send.sort()
            for (bln, text) in to_send:
                logger.info("Posting bulletin: %s=%s", bln, text)
                self._aprs.send_aprs_msg(bln, text)


# These lines are for maintaining the net logs. Basically the netlog file is just a temporary file for storing a single checkin.
# APRS sends multiple tries, thus a callsign might be duplicated. So each "net" message overwrites this file, which is then processed
# Into a comma-separated file (for replying to LOG messages) and a line-separated file (for processing CQ messages).

        if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/netlog'):
           file = open('/home/pi/ioreth/ioreth/ioreth/netlog', 'r')
           data2 = file.read()  
           file.close()
           fout = open(filename1, 'a')
           fout.write(data2)
           fout.write(",")
           fout = open(filename3, 'a')
           fout.write(data2)
           fout.write("\n")
           logger.info("Copying latest checkin into day's net logs")
           os.remove('/home/pi/ioreth/ioreth/ioreth/netlog')
           logger.info("Deleting net log scratch file")
           file = open(filename1, 'r')
           data5 = file.read()  
           file.close()
            
# These lines below send a bulletin update with the latest checkins.            
           self._aprs.send_aprs_msg("BLN8NET", timestr + ": " + data5)
           self._aprs.send_aprs_msg("BLN9NET", "Full msg logs at http://aprs.dx1arm.net")
           logger.info("Sending new log text to BLN8NET after copying over to daily log")
           return

        if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/nettext'):
           file = open('/home/pi/ioreth/ioreth/ioreth/nettext', 'r')
           data4 = file.read()  
           file.close()
           fout = open('/home/pi/ioreth/ioreth/ioreth/netlog-msg', 'a')
           fout.write(data4)
           fout.write("\n")
           logger.info("Copying latest checkin message into cumulative net log")
           os.remove('/home/pi/ioreth/ioreth/ioreth/nettext')
           logger.info("Deleting net text scratch file")
           return

    def send_aprs_msg(self, to_call, text):
        self._client.enqueue_frame(self.make_aprs_msg(to_call, text))

    def _update_status(self):
        if not self._cfg.has_section("status"):
            return

        max_age = self._cfg.getint("status", "send_freq", fallback=600)
        now_mono = time.monotonic()
        if now_mono < (self._last_status + max_age):
            return

        self._last_status = now_mono
        self._rem.post_cmd(SystemStatusCommand(self._cfg["status"]))



    def _check_reconnection(self):
        if self.is_connected():
            return
        try:
            # Server is in localhost, no need for a fancy exponential backoff.
            if time.monotonic() > self._last_reconnect_attempt + 5:
                logger.info("Trying to reconnect")
                self._last_reconnect_attempt = time.monotonic()
                self.connect()
        except ConnectionRefusedError as e:
            logger.warning(e)

    def on_loop_hook(self):
        AprsClient.on_loop_hook(self)
        self._check_updated_config()
        self._check_reconnection()
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
