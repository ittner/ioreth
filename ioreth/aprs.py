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

logging.basicConfig()
logger = logging.getLogger(__name__)

from . import ax25


class Handler:
    """Handle parsing and generation of APRS packets.
    """

    DEFAULT_PATH = "WIDE1-1,WIDE2-2"
    DEFAULT_DESTINATION = "APZIOR"

    def __init__(self, callsign="XX0ABC"):
        self.callsign = callsign
        self.destination = Handler.DEFAULT_DESTINATION
        self.path = Handler.DEFAULT_PATH

    def make_frame(self, data):
        """Shortcut for making a AX.25 frame with a APRS packet with the
        known (mostly constant) information and 'data' as the contents.
        """
        return ax25.Frame(
            ax25.Address.from_string(self.callsign),
            ax25.Address.from_string(self.destination),
            [ax25.Address.from_string(s) for s in self.path.split(",")],
            ax25.APRS_CONTROL_FLD,
            ax25.APRS_PROTOCOL_ID,
            data,
        )

    def make_aprs_msg(self, to_call, text):
        """Make an APRS message packet sending 'text' to 'to_call'.
        """
        addr_msg = ":" + to_call.ljust(9, " ") + ":" + text
        return self.make_frame(addr_msg.encode("utf-8"))

    def make_aprs_status(self, status):
        """Make an APRS status packet.
        """
        return self.make_frame((">" + status).encode("utf-8"))

    def handle_frame(self, frame):
        """ Handle an AX.25 frame and looks for APRS data packets.
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
            self._handle_aprs_message(origframe, source, payload, via)
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

    def _handle_aprs_message(self, origframe, source, payload, via):
        """Parse APRS message packet (data type: :)

        This may be a directed message, a bulletin, announce ... with or
        without confirmation request, or maybe just trash. We will need to
        look inside to know.
        """
        data_str = payload.decode("utf-8", errors="replace")

        addressee_text = data_str[1:].split(":", 1)
        if len(addressee_text) != 2:
            logger.warning("Bad addressee:text pair: %s", addressee_text)
            return
        addressee = addressee_text[0].strip()
        text_msgid = addressee_text[1].rsplit("{", 1)
        text = text_msgid[0]
        msgid = None
        if len(text_msgid) == 2:
            # This message is asking for an ack.
            msgid = text_msgid[1]

        logger.info("Message from %s: %s", source, text)
        self.on_aprs_message(source, addressee, text, origframe, msgid, via)

    def on_aprs_message(self, source, addressee, text, origframe, msgid=None, via=None):
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
