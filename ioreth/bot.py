import sys
import time
import logging
import configparser
import os
import re

logging.basicConfig()
logger = logging.getLogger(__name__)

from .clients import AprsClient


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
        """Received an AX.25 frame. It *may* have an APRS packet.
        """

        if frame.info == b"":
            # No data.
            return

        via = None
        source = frame.source.to_string()
        payload = frame.info

        if payload[0] == ord(b"}"):
            # Got a third-party APRS packet, check the payload.
            # PP5ITT-10>APDW15,PP5JRS-15*,WIDE2-1:}PP5ITT-7>APDR15,TCPIP,PP5ITT-10*::PP5ITT-10:ping 00:01{17

            # This is tricky: according to the APRS Protocol Reference 1.0.1,
            # chapter 17, the path may be both in TNC-2 encoding or in AEA
            # encoding. So these both are valid:
            #
            # S0URCE>DE5T,PA0TH,PA1TH:payload
            # S0URCE>PA0TH>PA1TH>DE5T:payload
            #
            # We are only using the source and payload for now so no worries,
            # but another parser will be needed if we want the path.
            #
            # Of course, I never saw one of these EAE paths in the wild.

            via = source
            src_rest = frame.info[1:].split(b">", 1)
            if len(src_rest) != 2:
                logger.debug(
                    "Discarding third party packet with no destination. %s",
                    frame.to_aprs_string().decode("utf-8", errors="replace"),
                )
                return

            # Source address should be a valid callsign+SSID.
            source = src_rest[0].decode("utf-8", errors="replace")
            destpath_payload = src_rest[1].split(b":", 1)

            if len(destpath_payload) != 2:
                logger.debug(
                    "Discarding third party packet with no payload. %s",
                    frame.to_aprs_string().decode("utf-8", errors="replace"),
                )
                return

            payload = destpath_payload[1]

        self.handle_aprs_packet(frame, source, payload, via)

    def handle_aprs_packet(self, origframe, source, payload, via=None):
        """Got an APRS packet, possibly through a third-party forward.

        origframe: the original ax25.Frame
        source: the sender's callsign as a string.
        payload: the APRS data as bytes.
        via: None is not a third party packet; otherwise is the callsign of the
             forwarder (as a string).
        """

        if payload[0] == ord(b":"):
            # APRS data type == ":". We got an message (directed, bulletin,
            # announce ... with or without confirmation request, or maybe
            # just trash. We will need to look inside to know.
            self.handle_aprs_msg(source, payload.decode("utf-8", errors="replace"))

        # Add support to other data types here.

    def handle_aprs_msg(self, source, data_str):
        """Handle an APRS message.

        This may be a directed message, a bulletin, announce ... with or
        without confirmation request, or maybe just trash. We will need to
        look inside to know.
        """

        addressee_text = data_str[1:].split(":", 1)
        if len(addressee_text) != 2:
            # Should be a destinatio_station : message
            return

        addressee = addressee_text[0].strip()
        if addressee.upper() != self.callsign.upper():
            # This message was not sent for us.
            return

        text_msgid = addressee_text[1].rsplit("{", 1)
        text = text_msgid[0]
        msgid = None
        if len(text_msgid) == 2:
            # This message is asking for an ack.
            msgid = text_msgid[1]

        logger.info("Message from %s: %s", source, text)
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
