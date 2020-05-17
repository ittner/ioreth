#!/usr/bin/env python3


import socket
import select
import sys
import time
import logging
import configparser
import os
import re

import ax25


logging.basicConfig(
    level=logging.INFO, format="%(asctime)-15s %(levelname)s: %(funcName)s %(message)s"
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class TcpKissClient:
    FEND = b"\xc0"
    FESC = b"\xdb"
    TFEND = b"\xdc"
    TFESC = b"\xdd"
    DATA = b"\x00"
    FESC_TFESC = FESC + TFESC
    FESC_TFEND = FESC + TFEND

    def __init__(self, addr="localhost", port=8001):
        self.addr = addr
        self.port = port
        self._sock = None
        self._inbuf = None
        self._outbuf = None
        self._run = False

    def connect(self):
        if self._sock:
            self.disconnect()
        self._inbuf = bytearray()
        self._outbuf = bytearray()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self.addr, self.port))
        self.on_connect()

    def disconnect(self):
        if self._sock:
            self._sock.close()
            self._sock = None
            self._inbuf = None
            self._outbuf = None
            self.on_disconnect()
        self.exit_loop()

    def loop(self):

        poller = select.poll()
        fd = self._sock.fileno()
        self._run = True
        disconnected = False

        while self._run:
            flags = select.POLLIN | select.POLLHUP | select.POLLERR
            if len(self._outbuf) > 0:
                flags |= select.POLLOUT
            poller.register(fd, flags)
            events = poller.poll(1000)

            # There is only one :/
            for _, evt in events:
                if evt & (select.POLLHUP | select.POLLERR):
                    disconnected = True

                if evt & select.POLLIN:
                    rdata = self._sock.recv(2048)
                    if len(rdata) == 0:
                        disconnected = True
                    else:
                        self._inbuf += rdata

                if evt & select.POLLOUT:
                    nsent = self._sock.send(self._outbuf)
                    self._outbuf = self._outbuf[nsent:]

            poller.unregister(fd)

            while len(self._inbuf) > 3:
                # FEND, FDATA, escaped_data, FEND, ...
                if self._inbuf[0] != ord(TcpKissClient.FEND):
                    raise ValueError("Bad frame start")
                lst = self._inbuf[2:].split(TcpKissClient.FEND, 1)
                if len(lst) > 1:
                    self._inbuf = lst[1]
                    frame = (
                        lst[0]
                        .replace(TcpKissClient.FESC_TFEND, TcpKissClient.FEND)
                        .replace(TcpKissClient.FESC_TFESC, TcpKissClient.FESC)
                    )
                    self.on_recv(frame)

            self.on_loop_hook()

            if disconnected:
                self.disconnect()

    def exit_loop(self):
        self._run = False

    def write_frame(self, frame_bytes):
        """Send a complete frame."""
        esc_frame = frame_bytes.replace(
            TcpKissClient.FESC, TcpKissClient.FESC_TFESC
        ).replace(TcpKissClient.FEND, TcpKissClient.FESC_TFEND)
        self._outbuf += (
            TcpKissClient.FEND + TcpKissClient.DATA + esc_frame + TcpKissClient.FEND
        )

    def on_connect(self):
        pass

    def on_recv(self, frame_bytes):
        pass

    def on_disconnect(self):
        pass

    def on_loop_hook(self):
        pass


class KissPrint(TcpKissClient):
    def on_connect(self):
        logger.info("Connected!")

    def on_recv(self, frame_bytes):
        try:
            f = ax25.Frame.from_kiss_bytes(frame_bytes)
            print(f)
        except Exception as exc:
            logger.warning(exc)

    def on_disconnect(self):
        logger.info("Disconnected!")
        self.connect()


class AprsClient(TcpKissClient):
    DEFAULT_PATH = "WIDE1-1,WIDE2-2"
    DEFAULT_DESTINATION = "APRS"

    def __init__(self, callsign="XX0ABC", host="localhost", port=8001):
        TcpKissClient.__init__(self, host, port)
        self.callsign = callsign
        self.destination = AprsClient.DEFAULT_DESTINATION
        self.path = AprsClient.DEFAULT_PATH
        self._snd_queue = []
        self._snd_queue_interval = 2
        self._snd_queue_last = time.monotonic()
        self._update_props()

    def _update_props(self):
        self._base_frame = ax25.Frame(
            ax25.Address.from_string(self.callsign),
            ax25.Address.from_string(self.destination),
            [ax25.Address.from_string(s) for s in self.path.split(",")],
            ax25.APRS_CONTROL_FLD,
            ax25.APRS_PROTOCOL_ID,
            b"",
        )

    def on_recv(self, frame_bytes):
        try:
            frame = ax25.Frame.from_kiss_bytes(frame_bytes)
            logger.info("RECV: %s", str(frame))
            self.on_recv_frame(frame)
        except Exception as exc:
            logger.warning(exc)

    def on_recv_frame(self, frame):
        pass

    def send_aprs_data(self, data_bytes):
        try:
            self._base_frame.info = data_bytes
            logger.info("SEND: %s", str(self._base_frame))
            self.write_frame(self._base_frame.to_kiss_bytes())
        except Exception as exc:
            logger.warning(exc)

    def enqueue_aprs_data(self, data_bytes):
        logger.info("APRS message enqueued for sending")
        self._snd_queue.append(data_bytes)

    def _dequeue_aprs(self):
        now = time.monotonic()
        if now < (self._snd_queue_last + self._snd_queue_interval):
            return
        self._snd_queue_last = now
        if len(self._snd_queue) > 0:
            logger.info("Sending queued APRS message")
            self.send_aprs_data(self._snd_queue.pop(0))

    def on_loop_hook(self):
        self._dequeue_aprs()


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


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: %s <config-file.conf>" % (sys.argv[0]))
        exit(1)
    b = ReplyBot(sys.argv[1])
    b.connect()
    b.loop()
