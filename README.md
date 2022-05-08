
# About

Ioreth is a **very experimental** APRS bot. There is a lot f things to be
done yet, including writing the documentation. For now, you are welcome to
use it as you want.

Note that transmitting on the usual APRS ham bands requires (at least) an
Amateur Radio license and additional conditions and limitations for this
particular mode of operation may apply on your country or region. You MUST
ensure compliance with your local regulations before transmitting, but all
other uses are only subjected to the GNU GPLv3+ (see license bellow).

Connecting this program to the APRS-IS network also requires a license as
you will be, effectively, operating remote transmitters through the Internet.




# License

Copyright (C) 2020  Alexandre Erwin Ittner, PP5ITT <alexandre@ittner.com.br>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.





# Contact information

Author: Alexandre Erwin Ittner   (callsign: PP5ITT)

Email: <alexandre@ittner.com.br>

Web: <https://www.ittner.com.br>



# Additional notes from Angelo DU2XXR / N2RAC

This fork of Ioreth was modified by Angelo DU2XXR / N2RAC to support additional
functionalities, such as a means to store callsigns from a "net" checkin
as well as a means to forward messages to all stations checked in for the day
It is also supported by local cron jobs on my own machine and web server
to publish the net log on a regular basis.
 
Pardon my code. My knowledge is very rudimentary, and I only modify or create
functions as I need them. If anyone can help improve on the code and the
logic of this script, I would very much appreciate it.
You may reach me at qsl@n2rac.com or simply APRS message me at N2RAC-7.

A lot of the items here are still poorly documented if at all. Many also
rely on some weird or nuanced scripts or directory structures that I have
maintained on my own machine or server, so bear with me.
The non-indented comments are mine. The indented ones are by Alexandre.
A lot of this is trial-and-error for me, so again, please bear with me.

# Supported bot commands

- *NET plus message* - This adds the user to the day's log (refreshes every midnight at the machine's local time). It also logs the timestamp, callsign, and message to a file that can be posted on the web. See http://aprs.dx1arm.net for example.
- *CQ plus message* - This sends the message to all stations currently checked into the net. It also saves the timestamp, callsign, and message to a file that can be posted on the web. See http://cq.dx1arm.net for example.
- *List* - returns a list of stations currently checked into the net.
- *Log* - Returns the last 3 net checkins and their messages.
- *Last* - Returns the last 3 CQ messages
- *SMS XXXXXXXXXXX Message* - Sends a text message the the number XXXXXXXXXXX along with the message. This supports replies or new messages from SMS users. Currently, the script is for numbers in the Philippines, since that is where I operate.
- *SMSALIAS XXXXXXXXXXX Message* - Sets an alias so that the SMS recipient/sender number will no longer appear in subsequent messages.
- *?APRST* or *?PING?* returns the path taken by the user's current ping message to the bot. 
- *TIME* returns the machine's current time.
- *VERSION* returns the python version.
- *HELP* returns a list of commands.
- Commands to run server-side commands are also supported.

# Contact information
- Email: qsl@n2rac.com
- Telegram: jangelor
- Web: <https://n2rac.com>
