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

"""
Random utilities for handling AX25 frames
"""


_ADDR_DIGIPEATED_BIT = 0b10000000
_ADDR_END_OF_PATH_BIT = 1

APRS_CONTROL_FLD = 0x03
APRS_PROTOCOL_ID = 0xF0


def pack_address(callsign, ssid=0, digipeated=False, end_of_path=False):
    if ssid < 0 or ssid > 15:
        raise ValueError("Bad SSID %d" % ssid)

    if len(callsign) > 6:
        raise ValueError("Callsign '%s' is too long" % callsign)

    addr = [a << 1 for a in callsign.ljust(6).encode("ASCII")]

    # Last byte format: h11sssse
    #   h = Has been digipeated;
    #   1 = Always one (reserved);
    #   s = SSID bits;
    #   e = End of repeater path.

    lastb = 0b01100000 | (ssid << 1)
    if digipeated:
        lastb |= _ADDR_DIGIPEATED_BIT
    if end_of_path:
        lastb |= _ADDR_END_OF_PATH_BIT
    addr.append(lastb)
    return bytes(addr)


def parse_address_string(addr_str):
    """Parse an AX25 address string into its components.

    The following formats are valid:

        PP5ITT      -- Callsign with no SSID;
        PP5ITT*     -- Digipeated callsign with no SSID;
        PP5ITT-10   -- Callsign with SSID;
        PP5ITT-10*  -- Digipeated callsign with SSID.
    """
    digipeated = False
    ssid = 0
    if addr_str[-1] == "*":
        digipeated = True
        addr_str = addr_str[:-1]
    lst = addr_str.split("-", 1)
    if len(lst) == 2:
        ssid = int(lst[1])
    return lst[0], ssid, digipeated


def pack_address_string(addr_str, end_of_path=False):
    """Pack an AX25 address string to a binary address.

    The following formats are valid:

        PP5ITT      -- Callsign with no SSID;
        PP5ITT*     -- Digipeated callsign with no SSID;
        PP5ITT-10   -- Callsign with SSID;
        PP5ITT-10*  -- Digipeated callsign with SSID.
    """

    callsign, ssid, digipeated = parse_address_string(addr_str)
    return pack_address(callsign, ssid, digipeated, end_of_path)


def unpack_address(addr):
    if len(addr) != 7:
        raise ValueError("Bad AX25 address")

    callsign = "".join(chr(n >> 1) for n in addr[0:6]).strip()
    ssid = (addr[6] & 0b00011110) >> 1
    digipeated = bool(addr[6] & _ADDR_DIGIPEATED_BIT)
    end_of_path = bool(addr[6] & _ADDR_END_OF_PATH_BIT)

    return callsign, ssid, digipeated, end_of_path


def format_address_to_string(callsign, ssid, digipeated):
    cs_pair = callsign
    if ssid != 0:
        cs_pair += "-%d" % (ssid)
    if digipeated:
        cs_pair += "*"
    return cs_pair


def unpack_address_to_string(addr):
    callsign, ssid, digipeated, _ = unpack_address(addr)
    return format_address_to_string(callsign, ssid, digipeated)


class Address:
    def __init__(self, callsign, ssid=0, digipeated=False, end_of_path=False):
        self.callsign = callsign
        self.ssid = ssid
        self.digipeated = digipeated
        self.end_of_path = end_of_path

    @staticmethod
    def from_bytes(addr):
        callsign, ssid, digipeated, end_of_path = unpack_address(addr)
        return Address(callsign, ssid, digipeated, end_of_path)

    @staticmethod
    def from_string(addr_str, end_of_path=False):
        callsign, ssid, digipeated = parse_address_string(addr_str)
        return Address(callsign, ssid, digipeated, end_of_path)

    def to_bytes(self):
        return pack_address(self.callsign, self.ssid, self.digipeated, self.end_of_path)

    def to_string(self):
        return format_address_to_string(self.callsign, self.ssid, self.digipeated)

    def __bytes__(self):
        return self.to_bytes()

    def __repr__(self):
        return self.to_string()

    def __str__(self):
        return self.to_string()


def pack_path(addr_strings):

    return b"".join(
        pack_address_string(a, False) for a in addr_strings[:-1]
    ) + pack_address_string(addr_strings[-1], True)


def unpack_path(path):

    if len(path) % 7 != 0:
        # It's an error: addresses are always 7 bytes long.
        raise ValueError("Invalid path length")

    return [unpack_address_to_string(path[i : i + 7]) for i in range(0, len(path), 7)]


def unpack_path_to_addrs(path):

    if len(path) % 7 != 0:
        # It's an error: addresses are always 7 bytes long.
        raise ValueError("Invalid path length")

    return [Address.from_bytes(path[i : i + 7]) for i in range(0, len(path), 7)]


class Frame:
    def __init__(self, source, dest, path, control, pid, info):
        self.source = source
        self.dest = dest
        self.path = path
        self.control = control
        self.pid = pid
        self.info = info

    @staticmethod
    def from_kiss_bytes(fdata):
        pos = 0
        dlen = len(fdata)
        if dlen < 19:
            raise ValueError(
                "Frame length is smaller than expected minimum. frame data: "
                + fdata.hex()
            )

        dest = Address.from_bytes(fdata[0:7])
        pos += 7

        addr_list = []
        while pos < dlen - 7:
            addr_list.append(Address.from_bytes(fdata[pos : pos + 7]))
            pos += 7
            if addr_list[-1].end_of_path:
                break

        source = addr_list[0]
        path = addr_list[1:]

        if pos >= dlen - 2:
            raise ValueError("Invalid frame data: " + fdata.hex())

        control = fdata[pos]
        pid = fdata[pos + 1]
        info = fdata[pos + 2 :]

        return Frame(source, dest, path, control, pid, info)

    def _update_end_of_path_flags(self):
        """Ensure "end of path" information is always valid.
        """
        self.source.end_of_path = False
        if len(self.path) > 0:
            self.dest.end_of_path = False
            for p in self.path:
                p.end_of_path = False
            self.path[-1].end_of_path = True
        else:
            self.dest.end_of_path = True

    def to_kiss_bytes(self):
        self._update_end_of_path_flags()
        return (
            self.dest.to_bytes()
            + self.source.to_bytes()
            + b"".join(p.to_bytes() for p in self.path)
            + bytes([self.control, self.pid])
            + self.info
        )

    @staticmethod
    def from_aprs_string(frame_str):
        """frame_str is a *bytes* object!  Rename this.
        """

        # PP5ITT-7>APDR15,PP5JRS-15*,WIDE2-2,qAR,PU5BRA-10:=2628.97S/04906.81Wx Ittner

        # Split the frame in headers and data
        lst = frame_str.split(b":", 1)
        if len(lst) != 2:
            raise ValueError("Bad APRS frame string")

        # Headers must be ASCII. Otherwhise is an error.
        headers = lst[0].decode("ascii")
        info = lst[1]

        lst = headers.split(">", 1)
        if len(lst) != 2:
            raise ValueError("Bad headers in APRS frame string")

        source = Address.from_string(lst[0])
        addrs = [Address.from_string(s) for s in lst[1].split(",")]
        if len(addrs) == 0:
            raise ValueError("No destination address in APRS frame string")

        dest = addrs[0]
        addrs[-1].end_of_path = True
        path = addrs[1:]

        f = Frame(source, dest, path, APRS_CONTROL_FLD, APRS_PROTOCOL_ID, info)
        f._update_end_of_path_flags()
        return f

    def to_aprs_string(self):
        """Convert the frame to a APRS string. Does not suport Mic-E yet.

        The APRS string is actually a *byte* string, despite the lion's
        share of the messages being ASCII-only.
        """

        buf = (
            self.source.to_string().encode("ASCII")
            + b">"
            + self.dest.to_string().encode("ASCII")
        )
        if len(self.path) > 0:
            buf += b"," + b",".join(a.to_string().encode("ASCII") for a in self.path)
        buf = buf + b":" + self.info

        return buf

    def __repr__(self):
        return self.to_aprs_string().decode("utf-8", errors="replace")
