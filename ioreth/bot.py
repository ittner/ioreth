import sys
import time
import logging
import configparser
import os
import re


from .clients import AprsClient


logging.basicConfig()
logger = logging.getLogger(__name__)


def is_br_callsign(callsign):
    return bool(re.match("P[PTUY][0-9].+", callsign.upper()))


class ReplyBot(AprsClient):
    def __init__(self, config_file):
        AprsClient.__init__(self)
        self._config_file = config_file
        self._config_mtime = None
        self._cfg = configparser.ConfigParser()
        self._check_updated_config()
        self._last_blns = time.monotonic()

    def _load_config(self):
        try:
            self._cfg.clear()
            self._cfg.read(self._config_file)
            self.addr = self._cfg["tnc"]["addr"]
            self.port = int(self._cfg["tnc"]["port"])
            self.callsign = self._cfg["aprs"]["callsign"]
            self.path = self._cfg["aprs"]["path"]
            self._update_props()
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
        if len(frame.info) == 0:
            # No data.
            return

        source = frame.source.to_string()
        data_str = frame.info.decode("utf-8", errors="replace")

        if data_str[0] == ":":
            # Got a direct APRS text message.
            self.handle_aprs_msg(source, data_str)

        elif data_str[0] == "}":
            # Got a third-party message, check the payload.
            # DEBUG RECV: PP5ITT-10>APDW15,PP5JRS-15*,WIDE2-1:}PP5ITT-7>APDR15,TCPIP,PP5ITT-10*::PP5ITT-10:ping 00:01{17
            via = source
            src_rest = data_str[1:].split(">", 1)
            if len(src_rest) != 2:
                # Unexpected format, nothing useful.
                return
            source = src_rest[0]
            path_msg = src_rest[1].split(":", 1)
            if len(path_msg) != 2:
                # No payload.
                return
            inner_msg = path_msg[1]
            if len(inner_msg) > 1 and inner_msg[0] == ":":
                logger.info("Got a third-party message via %s..." % via)
                self.handle_aprs_msg(source, inner_msg)

    def handle_aprs_msg(self, source, data_str):

        dest_txt = data_str[1:].split(":", 1)
        if len(dest_txt) != 2:
            # Should be a destination station : message
            return

        msg_sent_to = dest_txt[0].strip()
        if msg_sent_to.upper() != self.callsign.upper():
            # This message was not sent for us.
            return

        text_msgid = dest_txt[1].rsplit("{", 1)
        text = text_msgid[0]
        if len(text_msgid) == 2:
            # This message is asking for an ack.
            msgid = text_msgid[1]
        else:
            msgid = None

        logger.info("Message from %s: %s", source, text)

        qry_args = text.lstrip().split(" ", 1)
        qry = qry_args[0].lower()
        args = ""
        if len(qry_args) == 2:
            args = qry_args[1]

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
        else:
            if is_br_callsign(source):
                self.send_aprs_msg(
                    source, "Sou um bot. Envie 'help' para a lista de comandos"
                )
            else:
                self.send_aprs_msg(source, "I'm a bot. Send 'help' for command list")

        if msgid:
            logger.info("Sending ack...")
            self.send_aprs_msg(source, "ack" + msgid)

    def send_aprs_msg(self, to_call, text):
        data = ":" + to_call.ljust(9, " ") + ":" + text
        self.enqueue_aprs_data(data.encode("utf-8"))

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
            self.send_aprs_msg(bln, text)

    def on_loop_hook(self):
        AprsClient.on_loop_hook(self)
        self._check_updated_config()
        self._update_bulletins()
