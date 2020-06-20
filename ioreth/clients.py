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

import socket
import select
import time
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)

from . import ax25


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

    def is_connected(self):
        return bool(self._sock)

    def loop(self):
        poller = select.poll()
        self._run = True

        while self._run:
            will_disconnect = False
            fd = -1
            if self.is_connected():
                fd = self._sock.fileno()
                flags = select.POLLIN | select.POLLHUP | select.POLLERR
                if len(self._outbuf) > 0:
                    flags |= select.POLLOUT
                poller.register(fd, flags)

            events = poller.poll(1000)

            # There is only one :/
            for _, evt in events:
                if evt & (select.POLLHUP | select.POLLERR):
                    will_disconnect = True

                if evt & select.POLLIN:
                    rdata = self._sock.recv(2048)
                    if len(rdata) == 0:
                        will_disconnect = True
                    else:
                        self._inbuf += rdata

                if evt & select.POLLOUT:
                    nsent = self._sock.send(self._outbuf)
                    self._outbuf = self._outbuf[nsent:]

            if fd >= 0:
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

            if will_disconnect:
                self.disconnect()

    def exit_loop(self):
        self._run = False

    def write_frame(self, frame_bytes):
        """Send a complete frame."""
        if not self.is_connected():
            return
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


class AprsClient(TcpKissClient):
    def __init__(self, host="localhost", port=8001):
        TcpKissClient.__init__(self, host, port)
        self._snd_queue = []
        self._snd_queue_interval = 2
        self._snd_queue_last = time.monotonic()
        self._frame_cnt = 0

    def send_frame_bytes(self, frame_bytes):
        try:
            logger.debug("SEND: %s", frame_bytes.hex())
            self.write_frame(frame_bytes)
        except Exception as exc:
            logger.warning(exc)

    def on_recv(self, frame_bytes):
        try:
            frame = ax25.Frame.from_kiss_bytes(frame_bytes)
            logger.info("RECV: %s", str(frame))
            self.on_recv_frame(frame)
        except Exception as exc:
            logger.warning(exc)

    def on_recv_frame(self, frame):
        pass

    def enqueue_frame(self, frame):
        logger.debug("AX.25 frame %d: %s", self._frame_cnt, frame.to_aprs_string())
        self.enqueue_frame_bytes(frame.to_kiss_bytes())

    def enqueue_frame_bytes(self, data_bytes):
        logger.debug("AX.25 frame %d enqueued for sending", self._frame_cnt)
        self._snd_queue.append((self._frame_cnt, data_bytes))
        self._frame_cnt += 1

    def _dequeue_frame_bytes(self):
        now = time.monotonic()
        if now < (self._snd_queue_last + self._snd_queue_interval):
            return
        self._snd_queue_last = now
        if len(self._snd_queue) > 0:
            num, frame_bytes = self._snd_queue.pop(0)
            logger.debug("Sending queued AX.25 frame %d", num)
            self.send_frame_bytes(frame_bytes)

    def on_loop_hook(self):
        self._dequeue_frame_bytes()
