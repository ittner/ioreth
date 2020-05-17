import socket
import select
import time
import logging

from . import ax25

logging.basicConfig()
logger = logging.getLogger(__name__)


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
