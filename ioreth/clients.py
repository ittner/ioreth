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
            self._on_recv_frame(frame)
        except Exception as exc:
            logger.warning(exc)

    def _on_recv_frame(self, frame):
        """ Handle a received frame and looks for APRS data packets.
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

        self.on_aprs_packet(frame, source, payload, via)

    def on_aprs_packet(self, origframe, source, payload, via=None):
        """A APRS packet was received, possibly through a third-party forward.

        This code runs *after* the search for third-party packets. The
        default implementation will call a more specialized callback for
        known data types. Users can override this for specialized parsing
        if required.

        origframe: the original ax25.Frame
        source: the sender's callsign as a string.
        payload: the APRS data as bytes.
        via: None is not a third party packet; otherwise is the callsign of
             the forwarder (as a string).
        """
        if payload == b"":
            self.on_aprs_empty(origframe, source, payload, via)
            return
        data_type = payload[0]
        if data_type == ord(b":"):
            self.on_aprs_message(origframe, source, payload, via)
        elif data_type == ord(b">"):
            self.on_aprs_status(origframe, source, payload, via)
        elif data_type == ord(b";"):
            self.on_aprs_object(origframe, source, payload, via)
        elif data_type == ord(b")"):
            self.on_aprs_item(origframe, source, payload, via)
        elif data_type == ord(b"?"):
            self.on_aprs_query(origframe, source, payload, via)
        elif data_type == ord(b"<"):
            self.on_aprs_capabilities(origframe, source, payload, via)
        elif data_type == ord(b"!"):
            self.on_aprs_position_wtr(origframe, source, payload, via)
        elif data_type == ord(b"@"):
            self.on_aprs_position_ts_msg(origframe, source, payload, via)
        elif data_type == ord(b"="):
            self.on_aprs_position_msg(origframe, source, payload, via)
        elif data_type == ord(b"/"):
            self.on_aprs_position_ts(origframe, source, payload, via)
        elif data_type == ord(b"T"):
            self.on_aprs_telemetry(origframe, source, payload, via)
        elif data_type == ord(b"`"):
            self.on_aprs_mic_e(origframe, source, payload, via)
        elif data_type == ord(b"'"):
            self.on_aprs_old_mic_e(origframe, source, payload, via)
        else:
            self.on_aprs_others(origframe, source, payload, via)

    def on_aprs_empty(self, origframe, source, payload, via):
        """APRS empty packet (no payload). What can we do with this?! Just
        log the sending station as alive?
        """
        pass

    def on_aprs_message(self, origframe, source, payload, via=None):
        """APRS message packet (data type: :)
        """
        pass

    def on_aprs_status(self, origframe, source, payload, via=None):
        """APRS status packet (data type: >)
        """
        pass

    def on_aprs_object(self, origframe, source, payload, via=None):
        """Object packet (data type: ;)
        """
        pass

    def on_aprs_item(self, origframe, source, payload, via=None):
        """Object packet (data type: ))
        """
        pass

    def on_aprs_query(self, origframe, source, payload, via=None):
        """APRS query packet (data type: ?)
        """
        pass

    def on_aprs_capabilities(self, origframe, source, payload, via=None):
        """Station capabilities packet (data type: <)
        """
        pass

    def on_aprs_position_wtr(self, origframe, source, payload, via=None):
        """Position without timestamp no APRS messaging, or Ultimeter
        2000 WX Station (data type: !)

        This mix-up with weather data is pure madness.

        eg.
        PP5JRS-15>APBK20,WIDE1-1,WIDE2-1:!2630.96S/04903.24W#digipeater de Jaragua do Sul - SC
        PP5JR-15>APNU3B,WIDE1-1,WIDE3-3:!2741.46S/04908.89W#PHG7460/REDE SUL APRS BOA VISTA RANCHO QUEIMADO SC
        PY5CTV-13>APTT4,PP5BAU-15*,PP5JRS-15*:! Weather Station ISS Davis Morro do Caratuva - PR
        """
        pass

    def on_aprs_position_ts_msg(self, origframe, source, payload, via=None):
        """Position with timestamp (with APRS messaging) (data type: @)

        eg.
        PP5JR-13>APRS,PP5JR-15*,PP5JRS-15*:@092248z2741.47S/04908.88W_098/011g014t057r000p000P000h60b07816.DsVP
        """
        pass

    def on_aprs_position_msg(self, origframe, source, payload, via=None):
        """Position without timestamp with APRS messaging (data type: =)

        eg.
        PY5TJ-12>APBK,PY5CTV-13*,WIDE1*,PP5JRS-15*:=2532.12S/04914.18WkTelemetria: 14.6v 25*C 56% U. Rel
        """
        pass

    def on_aprs_position_ts(self, origframe, source, payload, via=None):
        """Position with timestamp, no APRS messaging (data type: /)
        """
        pass

    def on_aprs_telemetry(self, origframe, source, payload, via=None):
        """Telemetry packet (data type: T)
        """
        pass

    def on_aprs_mic_e(self, origframe, source, payload, via=None):
        """APRS Mic-E packet, current (data type: `)
        """
        pass

    def on_aprs_old_mic_e(self, origframe, source, payload, via=None):
        """APRS Mic-E packet, old (data type: ')
        """
        pass

    def on_aprs_others(self, origframe, source, payload, via=None):
        """All other APRS data types (possibly unknown)
        """
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
