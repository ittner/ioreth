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
# This fork of Ioreth was modified by Angelo N2RAC/DU2XXR to support additional
# functionalities, such as a means to store callsigns from a "net" checkin
# as well as a means to forward messages to all stations checked in for the day
# It is also supported by local cron jobs on my own machine and web server
# to publish the net log on a regular basis.
# 
# Pardon my code. My knowledge is very rudimentary, and I only modify or create
# functions as I need them. If anyone can help improve on the code and the
# logic of this script, I would very much appreciate it.
# You may reach me at qsl@n2rac.com or simply APRS message me at DU2XXR-7.
#
# A lot of the items here are still poorly documented if at all. Many also
# rely on some weird or nuanced scripts or directory structures that I have
# maintained on my own machine or server, so bear with me.
# The non-indented comments are mine. The indented ones are by Alexandre.
# A lot of this is trial-and-error for me, so again, please bear with me.
#
# 2024-02-09 0020H

import sys
import time
import logging
import configparser
import os
import re
import random
import urllib
import requests
import json
import datetime
from datetime import datetime
import calendar

logging.basicConfig()
logger = logging.getLogger(__name__)

from cronex import CronExpression
from .clients import AprsClient
from . import aprs
from . import remotecmd
from . import utils
from os import path
from urllib.request import urlopen, Request


# These lines below I have added in order to provide a means for ioreth to store
# and retrieve a list of "net" checkins on a daily basis. I did not bother to use
# more intuitive names for the files, but I can perhaps do so in a later code cleanup.

timestr = time.strftime("%Y%m%d")
filename1 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr
filename2 = "home/pi/ioreth/ioreth/ioreth/netlog-msg"
filename3 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr+"-cr"
cqmesg = "/home/pi/ioreth/ioreth/ioreth/cqlog/cqmesg"
cqlog = "/home/pi/ioreth/ioreth/ioreth/cqlog/cqlog"
dusubs = "/home/pi/ioreth/ioreth/ioreth/dusubs"
dusubslist = "/home/pi/ioreth/ioreth/ioreth/dusubslist"
file = open(filename1, 'a')
file = open(filename3, 'a')
icmesg = "/home/pi/ioreth/ioreth/ioreth/eric/icmesg"
iclist = "/home/pi/ioreth/ioreth/ioreth/eric/iclist"
iclog = "/home/pi/ioreth/ioreth/ioreth/eric/eric"
iclast = "/home/pi/ioreth/ioreth/ioreth/eric/iclast"
iclatest = "/home/pi/ioreth/ioreth/ioreth/eric/iclatest"
timestrtxt = time.strftime("%m%d")
aprsfiapi = ""

# Also moved time string to place where it can be reset at midnight

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

#        self.handle_aprs_msg_bot_query(source, text, origframe)
        if msgid:
            # APRS Protocol Reference 1.0.1 chapter 14 (page 72) says we can
            # reject a message by sending a rejXXXXX instead of an ackXXXXX
            # "If a station is unable to accept a message". Not sure if it is
            # semantically correct to use this for an invalid query for a bot,
            # so always acks.
            logger.info("Sending ack to message %s from %s.", msgid, source)
            self.send_aprs_msg(source.replace('*',''), "ack" + msgid)

        self.handle_aprs_msg_bot_query(source, text, origframe)


    def handle_aprs_msg_bot_query(self, source, text, origframe):
        """We got an text message direct to us. Handle it as a bot query.
        TODO: Make this a generic thing.

        source: the sender's callsign+SSID
        text: message text.
        """

        sourcetrunc = source.replace('*','')
        qry_args = text.lstrip().split(" ", 1)
        qry = qry_args[0].lower()
        qrynormalcase = qry_args[0]
        args = ""
        timestr = time.strftime("%Y%m%d")
        filename1 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr
        timestrtxt = time.strftime("%m%d %H%MZ")
        if not os.path.isfile(filename1):
            file = open(filename1, 'w')
        if not os.path.isfile(filename3):
            file = open(filename3, 'w')
        if len(qry_args) == 2:
            args = qry_args[1]

        random_replies = {
            "moria": "Pedo mellon a minno",
            "mellon": "*door opens*",
            "mellon!": "**door opens**  🚶🚶🚶🚶🚶🚶🚶🚶🚶  💍→🌋",
            "meow": "=^.^=  purr purr  =^.^=",
            "clacks": "GNU Terry Pratchett",
        }
        if '\x00' in args or '<0x' in args :
                  logger.info("Message contains null character from APRS looping issue. Stop processing." )
                  return

        if sourcetrunc == "APRSPH" or sourcetrunc == "ANSRVR" or sourcetrunc == "ID1OT" or sourcetrunc == "WLNK-1" or sourcetrunc == "KP4ASD" or qry[0:3] == "rej" or qry[0:3] == "aa:" or args == "may be unattended" or args =="QTH Digi heard you!" or qry == "aa:message" :
                  logger.info("Message from ignore list. Stop processing." )
                  return
#        if sourcetrunc == "ANSRVR":
#                  logger.info("Message from ANSRVR. Stop processing." )
#                  return



        if qry == "ping":
            timestrtxt = time.strftime("%m%d %H%MZ")
            self.send_aprs_msg(sourcetrunc, timestrtxt + ": Pong! " + args )
        elif qry == "test":
            timestrtxt = time.strftime("%m%d %H%MZ")
#                                               1234567890123456789012345678901234567890123456789012345678901234567
            self.send_aprs_msg(sourcetrunc, timestrtxt + ":It works! HELP for more commands. Info at aprsph.net")
        elif qry == "?aprst" or qry == "?ping?" or qry == "aprst?" or qry == "aprst" :
            tmp_lst = (
                origframe.to_aprs_string()
                .decode("utf-8", errors="replace")
                .split("::", 2)
            )
            self.send_aprs_msg(sourcetrunc, tmp_lst[0] + ":")
        elif qry == "version":
            self.send_aprs_msg(sourcetrunc, "Python " + sys.version.replace("\n", " "))
        elif qry == "about":
            self.send_aprs_msg(sourcetrunc, "APRS bot by N2RAC/DU2XXR based on ioreth by PP5ITT. aprsph.net" )
        elif qry == "time":
            self.send_aprs_msg(
                sourcetrunc, "Localtime is " + time.strftime("%Y-%m-%d %H:%M:%S %Z")
            )
        elif qry in ["help", "help ", "?", "? ", "aprsph.net", "aprsph.net "] :
            timestrtxt = time.strftime("%m%d")
#                                            123456789012345678901234567890123456789012345678901234567890123       4567
            self.send_aprs_msg(sourcetrunc, "CQ [space] msg to join net & send msg to all checked in today /" +timestrtxt)
            self.send_aprs_msg(sourcetrunc, "NET [space] msg to checkin & join without notifying everyone /" +timestrtxt)
            self.send_aprs_msg(sourcetrunc, "LAST/LAST10/LAST15 to retrieve 5/10/15 msgs. ?APRST for path /"+timestrtxt)
            self.send_aprs_msg(sourcetrunc, "SMS [spc] 09XXnumber [spc] msg to text PHILIPPINE numbers /" +timestrtxt)
            self.send_aprs_msg(sourcetrunc, "?APRSM for the last 10 direct msgs to you. U to leave the net /" +timestrtxt)
            self.send_aprs_msg(sourcetrunc, "MINE for ur last net msgs. SEARCH [spc] phrase to find msgs /" +timestrtxt)
            self.send_aprs_msg(sourcetrunc, "LIST to see today's checkins. https://aprsph.net for more info/"+timestrtxt)

        elif qry in ["?aprsp", "?aprs", "position", "position ", "p" "p "] :
            timestrtxt = time.strftime("%m%d %H%MZ")
            cmd1 = "cat /home/pi/aprsph-beacon | kissutil"
            self.send_aprs_msg(sourcetrunc, timestrtxt + " Sending position...I'm based at PK04 in the Philippines.")
#            try:
            os.system(cmd1)
            logger.info("Sending position packet.")
#            except:
        elif qry in ["?aprss", "status", "status ", "?aprss "] :
#            self._client.enqueue_frame(self.make_aprs_status(status))
            timestr = time.strftime("%Y%m%d")
            filename1 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr
            timestrtxt = time.strftime("%m%d %H%MZ")
            daylog = open(filename1, 'r')
            dayta2 = daylog.read() 
            daylog.close()
            dayta3 = dayta2.replace('\n','')
            count = 0
            for i in dayta3:
                         if i == ',':
                            count = count + 1

            strcount = str(count)
            smsrxnum = open('/home/pi/ioreth/ioreth/ioreth/smsrxcount', 'r')
            smsrxcounts = smsrxnum.read()
#        smsrxtotals1 = smsrxcounts.replace('total ','')
            smsrxtotals = smsrxcounts.replace('\n','')
            smsrxnum.close()

            smstxnum = open('/home/pi/ioreth/ioreth/ioreth/smstxcount', 'r')
            smstxcounts = smstxnum.read()
#        smstxtotals1 = smstxcounts.replace('total ','')
            smstxtotals = smstxcounts.replace('\n','')
            smstxnum.close()
            self.send_aprs_msg(sourcetrunc, timestrtxt + " " + strcount + " checkins. SMS Tx" + smstxtotals + " Rx" + smsrxtotals + ". aprsph.net info.")
            status_str = "NET join.HELP cmds. DU2XXR/1 aprsph.net. "
            self.send_aprs_status(status_str + strcount + " checkins. SMS T" + smstxtotals + " R" + smsrxtotals + " " + timestrtxt)
            logger.info("Sending status packet.")


# CQ[space]msg to join,LIST for net,LAST for log. More at aprsph.net.")

# This part is the net checkin. It logs callsigns into a daily list, and it also logs all messages into a cumulative list posted on the web

        elif qry == "ack" and args == "" :
                  logger.info("ACK. Ignoring." )

#This logs messages sent via APRSThursday
        elif qry in ["n:hotg", "n:hotg ", "hotg", "hotg "] :
           sourcetrunc = source.replace('*','')
           timestrtxt = time.strftime("%m%d %H%MZ")
# Checking if duplicate message
# If not, write msg to temp file
           dupecheck = qry + " " + args
           dt = datetime.now()
           if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/lastmsgdirthurs/' + sourcetrunc) and dupecheck == open('/home/pi/ioreth/ioreth/ioreth/lastmsgdirthurs/' + sourcetrunc).read():
                  logger.info("Message is exact duplicate. Stop logging." )
                  return
           else:
                  logger.info("Message is not exact duplicate, now logging" )

                  with open('/home/pi/ioreth/ioreth/ioreth/aprsthursdaytext', 'w') as g:
                       if dt.isoweekday() == 4 :
                           data3 = "{} {}:{} [#APRSThursday]".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
#                       if dt.isoweekday() == 4 and qry == "hotg" :
#                           data3 = "{} {}:{} [#APRSThursday] *".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
                       else :
                           data3 = "{} {}:{}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
                       if qry == "hotg" :
                           data3 = data3 + " *"
                           cmd1 = "echo -e '[0] " + sourcetrunc + ">APZIOR::YD0BCX-7 :N:HOTG " + args + "\n[0] " + sourcetrunc + ">APZIOR::YD0BCX-9 :N:HOTG " + args + "\n' | kissutil"
#                           cmd2 = "echo '[0] " + sourcetrunc + ">APZIOR::YD0BCX-9 :N:HOTG " + args + "' | kissutil"
#                           cmd3 = cmd1 + "; " + cmd2
#                           try:
                           os.system(cmd1)
#                           try:
#                           os.system(cmd2)

                           logger.info("Also forwarding the message from %s to YD0BCX", sourcetrunc)


                       g.write(data3)
                       logger.info("Writing %s net message to netlog text", sourcetrunc)
                       fout = open('/home/pi/ioreth/ioreth/ioreth/aprsthursday/index.html', 'a')
                       fout.write(data3)
                       fout.write("\n")
                       fout.close()
                       logger.info("Writing latest checkin message into APRSThursday net log")
#                                                        1234567890123456789012345678901234567890123456789012345678901234567
                  if dt.isoweekday() == 4 or qry == "hotg" :
                        self.send_aprs_msg(sourcetrunc, "Logged:" + timestrtxt + " https://aprsph.net/aprsthursday -KC8OWL & DU2XXR")
                        logger.info("It's Thursday. Notifing %s that their message is logged.", sourcetrunc)
                  else:
                        logger.info("It's not Thursday, so just logging %s message to HOTG.", sourcetrunc)
# Record the message somewhere to check if next message is dupe
                  dupecheck = qry + " " + args
                  with open('/home/pi/ioreth/ioreth/ioreth/lastmsgdirthurs/' + sourcetrunc, 'w') as g:
                        lasttext = args
                        g.write(dupecheck)
                        logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)
                        g.close()




        elif qry == "aprsthursday" :
#                                                   1234567890123456789012345678901234567890123456789012345678901234567
                      self.send_aprs_msg("ANSRVR", "CQ hotg joining #APRSThursday. Also checkin at https://aprsph.net")
                      logger.info("Joining APRSThursday")

        elif qry == "aprstsubs" :
#                                                   1234567890123456789012345678901234567890123456789012345678901234567
                      self.send_aprs_msg("ANSRVR", "j hotg")
                      logger.info("Joining APRSThursday")


        elif qry in ["u", "u ", "unsubscribe", "unsubscribe ", "checkout", "checkout ", "leave", "leave ", "exit", "exit "] :
# == "u" or qry == "unsubscribe" or qry == "checkout" or qry == "leave"  :
 

# Checking if already in log
           with open(filename3, 'r') as file:
                 timestrtxt = time.strftime("%m%d %H%MZ")
                 search_word = sourcetrunc 
                 search_replace = search_word + ","
                 if(search_word in file.read()):
#                                                      1234567890123456789012345678901234567890123456789012345678901234567
                      self.send_aprs_msg(sourcetrunc, "Unsubscribing from net " + timestrtxt +". NET or CQ to join again.")
                      logger.info("Found %s in today's net. Unsubscribing", sourcetrunc)
# Remove them from the day's list
                      with open(filename1, 'r') as file1:
                           filedata = file1.read()
                           filedata = filedata.replace(search_replace, '')
                      with open(filename1, 'w') as file1:
                           file1.write(filedata)

# Now remove them from the send list
                      with open(filename3, 'r') as file2:
                           filedata = file2.read()
                           sourcen = sourcetrunc + "\n"
                           filedata = filedata.replace(sourcen, '')
                      with open(filename3, 'w') as file2:
                           file2.write(filedata)

                      file2.close()

                      with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as g:
                           data3 = "{} {}:{} [Checked out from the net]".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
                           g.write(data3)
                           logger.info("Writing %s unsubscribe and message into netlog text", sourcetrunc)
                           fout = open('/home/pi/ioreth/ioreth/ioreth/netlog-msg', 'a')
                           fout.write(data3)
                           fout.write("\n")
                           fout.close()
                           logger.info("Writing unsubscribe message into cumulative log.")



# If not in log, then add them
                 else:
                      timestrtxt = time.strftime("%m%d")
                      self.send_aprs_msg(sourcetrunc, "Ur not checked in today " + timestrtxt + ". NET or CQ to join the net.")
                      logger.info("Replying to %s that they are not yet subscribed", sourcetrunc)


        elif qry in ["net", "check", "checkin", "checking", "checking ",  "joining", "join", "qrx", "k", "check-in", "net "] :
#  == "net" or qry == "checking" or qry == "check" or qry == "checkin" or qry == "joining" or qry == "join" or qry == "qrx" or qry == "j"  :
           sourcetrunc = source.replace('*','')
# Checking if duplicate message
# If not, write msg to temp file
           dupecheck = qry + " " + args
           argsstr1 = args.replace('<','&lt;')
           argsstr = argsstr1.replace('>','&gt;')
           if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc) and dupecheck == open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc).read():
                  logger.info("Message is exact duplicate. Stop logging." )
                  return
           else:
#           if not dupecheck == open('/home/pi/ioreth/ioreth/ioreth/lastmsg').read():
                  logger.info("Message is not exact duplicate, now logging" )

                  with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as g:
                       if qry == "net":
                          data3 = "{} {}:{} *".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, argsstr)
                       else:
                          data3 = "{} {}:{} {} *".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, qrynormalcase, argsstr)
                       g.write(data3)
                       logger.info("Writing %s net message to netlog text", sourcetrunc)
                       fout = open('/home/pi/ioreth/ioreth/ioreth/netlog-msg', 'a')
                       fout.write(data3)
                       fout.write("\n")
                       fout.close()
                       logger.info("Writing latest checkin message into cumulative net log")




# Checking if already in log
           with open(filename3, 'r') as file:
                 timestrtxt = time.strftime("%m%d %H%MZ")
                 search_word = sourcetrunc
                 if(search_word in file.read()):
#                                                      1234567890123456789012       345678901234567890123456789012345678901234567
                      self.send_aprs_msg(sourcetrunc, "QSL new msg " + timestrtxt +".CQ[spc]msg,LIST,LAST.Info:HELP or aprsph.net")
                      logger.info("Checked if %s already logged to prevent duplicate. Skipping checkin", sourcetrunc)
                      file.close()
# If not in log, then add them
                 else:
                      timestrtxt = time.strftime("%m%d")
                      with open('/home/pi/ioreth/ioreth/ioreth/netlog', 'w') as f:
                         f.write(sourcetrunc)
                         f.close()
                         logger.info("Writing %s checkin to netlog", source)
                      if args == "":
#                                                         1234567890123456789012345678901234567890123456789012345678901234567
                         self.send_aprs_msg(sourcetrunc, "U may also add msg.CQ[spc]msg.LAST for history.LIST for recipients")
#                      else:
#                                                      1234567890123          4    5678          9012345678901234567890123456789012345678901234567
                      self.send_aprs_msg(sourcetrunc, "QSL " + sourcetrunc + " " + timestrtxt + ". LAST view history. LIST recipients. U to leave")
#                                                      123456789012345678901           2345678901234567890123456789012345678901234567
                      self.send_aprs_msg(sourcetrunc, "Stdby 4 msgs til "+timestrtxt+ " 2359Z.CQ[spc]msg QSP. Info:HELP or aprsph.net" )
                      logger.info("Replying to %s checkin message", sourcetrunc)

# Record the message somewhere to check if next message is dupe
           dupecheck = qry + " " + args
           with open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc, 'w') as g:
                lasttext = args
                g.write(dupecheck)
                logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)
                g.close()

        elif qry == "list" or qry == "?aprsd" or qry == "qni" :
           sourcetrunc = source.replace('*','')
           timestrtxt = time.strftime("%m%d")
           if os.path.isfile(filename1):
                 file = open(filename1, 'r')
                 data21 = file.read()
                 data2 = data21.replace('\n','')
                 file.close()

                 if len(data2) > 373:
                       listbody1 = data2[0:58]
                       listbody2 = data2[58:121]
                       listbody3 = data2[121:184]
                       listbody4 = data2[184:247]
                       listbody5 = data2[247:310]
                       listbody6 = data2[310:]
                       self.send_aprs_msg(sourcetrunc, timestrtxt + " 1/7:" + listbody1 )
                       self.send_aprs_msg(sourcetrunc, "2/7:" + listbody2 )
                       self.send_aprs_msg(sourcetrunc, "3/7:" + listbody3 )
                       self.send_aprs_msg(sourcetrunc, "4/7:" + listbody4 )
                       self.send_aprs_msg(sourcetrunc, "5/7:" + listbody5 )
                       self.send_aprs_msg(sourcetrunc, "6/7:" + listbody6 )
                       self.send_aprs_msg(sourcetrunc, "7/7:+More stations. Refer https://aprsph.net for today's full log." )
#                       self.send_aprs_msg(sourcetrunc, "CQ[space]text to join & msg all in today's net. Info: aprsph.net" )
#                                                       1234567890123456789012345678901234567890123456789012345678901234567
                       logger.info("Replying with stations heard today. Exceeded length so split into 7 and advised to go to website: %s", data2 )
                 if len(data2) > 310 and len(data2) <=373 :
                       listbody1 = data2[0:58]
                       listbody2 = data2[58:121]
                       listbody3 = data2[121:184]
                       listbody4 = data2[184:247]
                       listbody5 = data2[247:310]
                       listbody6 = data2[310:]
                       self.send_aprs_msg(sourcetrunc, timestrtxt + " 1/6:" + listbody1 )
                       self.send_aprs_msg(sourcetrunc, "2/6:" + listbody2 )
                       self.send_aprs_msg(sourcetrunc, "3/6:" + listbody3 )
                       self.send_aprs_msg(sourcetrunc, "4/6:" + listbody4 )
                       self.send_aprs_msg(sourcetrunc, "5/6:" + listbody5 )
                       self.send_aprs_msg(sourcetrunc, "6/6:" + listbody6 )
#                       self.send_aprs_msg(sourcetrunc, "CQ[space]text to join & msg all in today's net. Info: aprsph.net" )
#                                                       1234567890123456789012345678901234567890123456789012345678901234567
                       logger.info("Replying with stations heard today. Exceeded length so split into 6: %s", data2 )
                 if len(data2) > 247 and len(data2) <= 310 :
                       listbody1 = data2[0:58]
                       listbody2 = data2[58:121]
                       listbody3 = data2[121:184]
                       listbody4 = data2[184:247]
                       listbody5 = data2[247:310]
                       self.send_aprs_msg(sourcetrunc, timestrtxt + " 1/5:" + listbody1 )
                       self.send_aprs_msg(sourcetrunc, "2/5:" + listbody2 )
                       self.send_aprs_msg(sourcetrunc, "3/5:" + listbody3 )
                       self.send_aprs_msg(sourcetrunc, "4/5:" + listbody4 )
                       self.send_aprs_msg(sourcetrunc, "5/5:" + listbody5 )
#                       self.send_aprs_msg(sourcetrunc, "CQ[space]text to join & msg all in today's net. Info: aprsph.net" )
#                       self.send_aprs_msg(sourcetrunc, "Send CQ +text to msg all in today's log. Info: aprsph.net" )
                       logger.info("Replying with stations heard today. Exceeded length so split into 5: %s", data2 )
                 if len(data2) > 184 and len(data2) <= 247 :
                       listbody1 = data2[0:58]
                       listbody2 = data2[58:121]
                       listbody3 = data2[121:184]
                       listbody4 = data2[184:]
                       self.send_aprs_msg(sourcetrunc, timestrtxt + " 1/4:" + listbody1 )
                       self.send_aprs_msg(sourcetrunc, "2/4:" + listbody2 )
                       self.send_aprs_msg(sourcetrunc, "3/4:" + listbody3 )
                       self.send_aprs_msg(sourcetrunc, "4/4:" + listbody4 )
#                       self.send_aprs_msg(sourcetrunc, "CQ[space]text to join & msg all in today's net. Info: aprsph.net" )
#                       self.send_aprs_msg(sourcetrunc, "Send CQ +text to msg all in today's log. Info: aprsph.net" )
                       logger.info("Replying with stations heard today. Exceeded length so split into 4: %s", data2 )
                 if len(data2) > 121 and len(data2) <= 184:
                       listbody1 = data2[0:58]
                       listbody2 = data2[58:121]
                       listbody3 = data2[121:]
                       self.send_aprs_msg(sourcetrunc, timestrtxt + " 1/3:" + listbody1 )
                       self.send_aprs_msg(sourcetrunc, "2/3:" + listbody2 )
                       self.send_aprs_msg(sourcetrunc, "3/3:" + listbody3 )
#                       self.send_aprs_msg(sourcetrunc, "CQ[space]text to join & msg all in today's net. Info: aprsph.net" )
#                       self.send_aprs_msg(source, "Send CQ +text to msg all in today's log. Info: aprsph.net" )
                       logger.info("Replying with stations heard today. Exceeded length so split into 3: %s", data2 )
                 if len(data2) > 58 and len(data2) <= 121:
                       listbody1 = data2[0:58]
                       listbody2 = data2[58:]
                       self.send_aprs_msg(sourcetrunc, timestrtxt + " 1/2:" + listbody1 )
                       self.send_aprs_msg(sourcetrunc, "2/2:" + listbody2 )
#                       self.send_aprs_msg(sourcetrunc, "CQ[space]text to join & msg all in today's net. Info: aprsph.net" )
#                       self.send_aprs_msg(sourcetrunc, "Send CQ +text to msg all in today's log. Info: aprsph.net" )
                       logger.info("Replying with stations heard today. Exceeded length so split into 2: %s", data2 )
                 if len(data2) <= 58:
                       self.send_aprs_msg(sourcetrunc, timestrtxt + ":" + data2 )
#                       self.send_aprs_msg(sourcetrunc, "CQ[space]text to join & msg all in today's net. Info: aprsph.net" )
#                       self.send_aprs_msg(sourcetrunc, "Send CQ +text to msg all in today's log. Info: aprsph.net" )
                       logger.info("Replying with stations heard today: %s", data2 )
#                                                 1234567890123456789012345678901234567890123456789012345678901234567
                 self.send_aprs_msg(sourcetrunc, "CQ[space]msg to join/chat. LAST for msg log. Info: aprsph.net" )
           else:
                 self.send_aprs_msg(sourcetrunc, "No stations checked in yet. CQ[space]msg to checkin.") 
        elif qry == "netremind" :
           lines = []
           sourcetrunc = source.replace('*','')
           with open(filename3) as sendlist:
                lines = sendlist.readlines()
           count = 0
           for line in lines:
                linetrunc = line.replace('\n','')
                count += 1
                strcount = str(count)
                timestrtxt = time.strftime("%m%d")
#                                   1234567890123456789012345678901234567890123456789012345678901234567
#                msgbody = timestrtxt + " This is a test message from the aprsph net manager."
                msgbody = timestrtxt + " net is restarting soon. Checkin again after 0000Z to rejoin."
                self.send_aprs_msg(linetrunc, msgbody )
                logger.info("Reminding %s that net will restart soon.", linetrunc)



        elif qry in ["cq", "hi", "hello", "happy","ga", "gm", "ge", "gn", "good", "gud", "gd", "ok", "j", "thanks", "tu", "tnx", "73", "greetings" ] :
           timestr = time.strftime("%Y%m%d")
           filename1 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr
           timestrtxt = time.strftime("%m%d %H%MZ")
           sourcetrunc = source.replace('*','')
           argsstr1 = args.replace('<','&lt;')
           argsstr = argsstr1.replace('>','&gt;')
           cqnet = 0
           nocheckins = 0
           dt = datetime.now()
# Checking if duplicate message
           dupecheck = qry + " " + args
           args2 = args.upper()
#           args2 = args2a.split(' ',1)[0]
           args3 = args[0:120]
           if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc) and dupecheck == open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc).read():
                  logger.info("Message is exact duplicate, stop logging." )
                  return
           if args2 in ["LIST", "LIST ", "LAST", "LAST ", "LAST10", "LAST10 ", "LAST15", "LAST15 ", "HELP", "HELP ", "APRSM?", "APRSM? " ] :
                        timestrtxt = time.strftime("%m%d:")
                        logger.info("CQ message is a command. Advising user to use the command without CQ" )
#                                                                1234567890123456789012345678901234567890123456789012345678901234567
                        self.send_aprs_msg(sourcetrunc, timestrtxt + "Are u trying to send a command? Try sending without CQ" )
                        self.send_aprs_msg(sourcetrunc, timestrtxt + "For example:" + args2 + " (without CQ before it)" )
                        self.send_aprs_msg(sourcetrunc, timestrtxt + "HELP for list of commands. More info at https://aprsph.net." )
# Changed the few lines below. Even if the user is sending a command as a message, log it anyway, but simply warn them.
#                        return
#           else:
           if args2.split(' ',1)[0] == "HOTG" and dt.isoweekday() == 4 :
# in ["LIST", "LIST ", "LAST", "LAST ", "LAST10", "LAST10 ", "LAST15", "LAST15 ", "HELP", "HELP ", "APRSM?", "APRSM? " ] :
                        timestrtxt = time.strftime("%m%d:")
                        logger.info("Possible APRSThursday checkin. Advise users to send without CQ" )
#                                                                1234567890123456789012345678901234567890123456789012345678901234567
                        self.send_aprs_msg(sourcetrunc, timestrtxt + "Trying to checkin APRSThursday? Send HOTG without CQ" )
                        self.send_aprs_msg(sourcetrunc, timestrtxt + "For example: HOTG [space] Your message here." )
                        self.send_aprs_msg(sourcetrunc, timestrtxt + "HELP for list of commands. More info at https://aprsph.net." )
           logger.info("Message is not exact duplicate, now logging" )
# This logs the message into net text draft for adding into the message log.
           with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as cqm:
                       if qry == "cq" :
                          data9 = "{} {}:{}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, argsstr)
                       else :
                          data9 = "{} {}:{} {}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, qrynormalcase, argsstr)
                       cqm.write(data9)
                       cqm.close()
                       logger.info("Writing %s CQ message to nettext", sourcetrunc)
                       fout = open('/home/pi/ioreth/ioreth/ioreth/netlog-msg', 'a')
                       fout.write(data9)
                       fout.write("\n")
                       fout.close()
                       logger.info("Writing latest checkin message into cumulative net log")

# If no checkins, we will check you in and also post your CQ message into the CQ log, and also include in net log
           if not os.path.isfile(filename3) :
               nocheckins = 1
               timestrtxt = time.strftime("%m%d")
               self.send_aprs_msg(sourcetrunc, "You are first in the day's log for " + timestrtxt + "." ) 
               with open('/home/pi/ioreth/ioreth/ioreth/netlog', 'w') as nt:
                   nt.write(sourcetrunc)
                   logger.info("Writing %S message to netlog", sourcetrunc)
# Checking if duplicate message
               dupecheck = qry + " " + args
               if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc) and dupecheck == open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc).read():
                   logger.info("Message is exact duplicate, stop logging" )
                   return
               else:
                   logger.info("Message is not exact duplicate, now logging" )
                   timestrtxt = time.strftime("%m%d:")
                   with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as ntg:
# If not duplicate, this logs the message into net text draft for adding into the message log.

                        if qry == "cq" :
                           data3 = "{} {}:{}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, argsstr)
                        else :
                           data3 = "{} {}:{} {}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, qrynormalcase, argsstr)
                        ntg.write(data3)
                        logger.info("Writing %s net message to netlog-msg", sourcetrunc)
                        fout = open('/home/pi/ioreth/ioreth/ioreth/netlog-msg', 'a')
                        fout.write(data3)
                        fout.write("\n")
                        fout.close()
                        logger.info("Writing latest checkin message into cumulative net log")

               logger.info("Advising %s to checkin", sourcetrunc)
               return
# If not yet in log, add them in and add their message to net log.
           file = open(filename3, 'r')
           search_word = sourcetrunc
           if not (search_word in file.read()):
                with open('/home/pi/ioreth/ioreth/ioreth/netlog', 'w') as cqf:
                      cqf.write(sourcetrunc)
                      logger.info("CQ source not yet in net. Writing %s checkin to netlog", source)

# Deprecated this part of the net, since CQs now default to the "Net" portion of the checkin (we have unified
# the checkin between CQ and Net). Perhaps we shall use another keyword for that purpose, since most people are
# Doing a Net and then a CQ afterward.
#                with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as ntg:
#                      if qry == "cq" :
#                         data3 = "{} {}:{}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
#                      else :
#                         data3 = "{} {}:{} {}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, qry, args)
#                      ntg.write(data3)
                      cqnet = 1
#                      logger.info("Writing %s net message to netlog-msg", sourcetrunc)
# Record the message somewhere to check if next message is dupe
           with open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc, 'w') as g:
                dupecheck = qry + " " + args
                g.write(dupecheck)
                logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)

# Send the message to all on the QRX list for today
           lines = []
           timestrtxt = time.strftime("%m%d")
           sourcetrunc = source.replace('*','')
           sendfile = "/home/pi/ioreth/ioreth/ioreth/outbox/" + sourcetrunc
           sendfile2 = "/home/pi/ioreth/ioreth/ioreth/outbox/" + sourcetrunc + "-reply"
           relay = "cat " + sendfile + " | kissutil"
           relay2 = "cat " + sendfile2 + " | kissutil"

           if os.path.isfile(sendfile):
                rmsendfile = ("sudo rm "+ sendfile)
                os.system(rmsendfile)
           if os.path.isfile(sendfile2):
                rmsendfile2 = ("sudo rm "+ sendfile2)
                os.system(rmsendfile2)

           with open(filename3) as sendlist:
                lines = sendlist.readlines()
           count = 0
           outboxfile = open(sendfile, 'a')
           replyfile = open(sendfile2, 'a')
# 123456789012345678901
           for line in lines:
                linetrunc = line.replace('\n','')
                linejust = linetrunc.ljust(9)
                count += 1
                strcount = str(count)
                msgbodycq = sourcetrunc + ":" + args
                msgbody = sourcetrunc + ":" + qrynormalcase + " " + args

                msgbodynewcq = "APRSPH:" + args
                msgbodynewcq2 = "APRSPH:" + qrynormalcase + " " + args


# 123456789012345678901
                if not sourcetrunc == linetrunc:
# Let's try a different logic for sending messages to the QRX list
                      groupreply = "[0] APRSPH>APZIOR,WIDE2-1::" + linejust + ":CQ[spc]msg to group reply.LIST recipients.LAST/LAST10 history " + timestrtxt
#                      replyfile.write(groupreply)
#                      replyfile.write("\n")
# 123456789012345678901
                      if qry == "cq" :
                         if len(msgbodycq) > 67 :
                            msgbody1 = msgbodycq[0:61]
                            msgbody2 = msgbodycq[61:118]
#                            self.send_aprs_msg(linetrunc, msgbody1 + "+" )
#                            self.send_aprs_msg(linetrunc, sourcetrunc + ":+" + msgbody2 )

                            draft1 = "[0] " + sourcetrunc + ">APZIOR,WIDE2-1::" + linejust + ":" + msgbodynewcq[0:62] + "+"
                            draft2 = "[0] " + sourcetrunc + ">APZIOR,WIDE2-1::" + linejust + ":" + msgbodynewcq[62:118]




#                            os.cmd("echo '" + draft1 + "' | kissutil" )
#                            os.cmd("echo '" + draft2 + "' | kissutil" )


                            outboxfile.write(draft1)
                            outboxfile.write("\n")
                            outboxfile.write(draft2)
                            outboxfile.write("\n")
                            outboxfile.write(groupreply)
                            outboxfile.write("\n")


                         else:
#                            self.send_aprs_msg(linetrunc, msgbodycq )

                            draft1 = "[0] " + sourcetrunc + ">APZIOR,WIDE2-1::" + linejust + ":" + msgbodynewcq
#                            os.cmd("echo '" + draft1 + "' | kissutil" )
                            outboxfile.write(draft1)
                            outboxfile.write("\n")
                            outboxfile.write(groupreply)
                            outboxfile.write("\n")




#                         self.send_aprs_msg(linetrunc, sourcetrunc + ":" + args)
                      else :
                         if len(msgbody) > 67 :
                            msgbody1 = msgbody[0:61]
                            msgbody2 = msgbody[61:118]
#                            self.send_aprs_msg(linetrunc, msgbody1 + "+" )
#                            self.send_aprs_msg(linetrunc, sourcetrunc + ":+" + msgbody2 )

                            draft1 = "[0] " + sourcetrunc + ">APZIOR,WIDE2-1::" + linejust + ":" + msgbodynewcq2[0:62] + "+"
                            draft2 = "[0] " + sourcetrunc + ">APZIOR,WIDE2-1::" + linejust + ":" + msgbodynewcq2[62:118]
#                            os.cmd("echo '" + draft1 + "' | kissutil" )
#                            os.cmd("echo '" + draft2 + "' | kissutil" )

                            outboxfile.write(draft1)
                            outboxfile.write("\n")
                            outboxfile.write(draft2)
                            outboxfile.write("\n")
                            outboxfile.write(groupreply)
                            outboxfile.write("\n")



                         else:
#                            self.send_aprs_msg(linetrunc, msgbody )
                            draft1 = "[0] " + sourcetrunc + ">APZIOR,WIDE2-1::" + linejust + ":" + msgbodynewcq2
#                            os.cmd("echo '" + draft1 + "' | kissutil" )

                            outboxfile.write(draft1)
                            outboxfile.write("\n")
                            outboxfile.write(groupreply)
                            outboxfile.write("\n")


#                         self.send_aprs_msg(linetrunc, sourcetrunc + ":" + qry + " " + args)
#                                                    1234567890123456789012345678901234567890123456789012345678901234567
# Rewrite message with original sender as FROM address
# 123456789012345678901

                      logger.info("Sending CQ message to %s except %s", linetrunc, sourcetrunc)
           outboxfile.close()
           os.system(relay)

#           replyfile.close()
#           os.system(relay2)
           logger.info("Sending message from %s via Kissutil", sourcetrunc)
#         except:
#               logger.info("Error sending message from %s via Kissutil", sourcetrunc)
      


#                      self.send_aprs_msg(linetrunc, "CQ[spc]msg to group reply.LIST recipients.LAST/LAST10 history " + timestrtxt  )
# This reads the day's log from a line-separated list for processing one message at a time.
# Advise sender their message is being processed/sent
           daylog = open(filename1, 'r')
           dayta2 = daylog.read() 
           daylog.close()
           dayta31 = dayta2.replace(sourcetrunc + ',','')
           dayta3 = dayta31.replace('\n','')
#           dayta3count = dayta3.count(",")
           if nocheckins == 1:
                 self.send_aprs_msg(sourcetrunc, "No CQ recipients yet. You are first in today's log." ) 
           else:
               timestrtxt = time.strftime("%m%d %H%MZ:")
               if len(dayta3) > 51 :
                     count = 0
                     for i in dayta3:
                         if i == ',':
                            count = count + 1
#                                                    12345678901   2345    67            89012345678901234567890123456789012345678901234567
                     self.send_aprs_msg(sourcetrunc, timestrtxt + "QSP " + str(count) + " stations. LIST for recipients. LAST for history." )
               elif len(dayta3) < 1:
                     timestrtxt = time.strftime("%m%d")
                     self.send_aprs_msg(sourcetrunc, "No other checkins yet. You are first in the log for " + timestrtxt )
               else:
#                                                    12345678901   23456789012345678901234567890123456789012345678901234567
                     self.send_aprs_msg(sourcetrunc, timestrtxt + "QSP "+ dayta3 )
           logger.info("Advising %s of messages sent to %s", sourcetrunc, dayta3)
           if cqnet == 1:
                 timestrtxt = time.strftime("%m%d %H%MZ")
#                                                 123456789012345678901234        5678901234567890123456789012345678901234567
                 self.send_aprs_msg(sourcetrunc, "Ur checked in " + timestrtxt + ". QRX pls til 2359Z. U to exit. aprsph.net" )
                 logger.info("Adivising %s they are also now checked in.", sourcetrunc)


# This option basically sends an SMS to DU2XXR's satellite phone. We may add additional phones as needed. Mostly for testing and proof of concept!

        elif qry == "sat" :
           sourcetrunc = source.replace('*','')
           satargs = args.replace('\"','')
           satargs2 = satargs.replace('\'','')
           satnum = satargs2.split(' ',1)[0]
           dupecheck = qry + " " + args
           timestrtxt = time.strftime("%m%d")
           if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc) and dupecheck == open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc).read():
                  logger.info("Message is exact duplicate, stop logging" )
                  return

           if not len(satnum) == 8 or satnum.isnumeric() == False  :
               logger.info("Error validating satellite message number from %s to %s", sourcetrunc,satnum)
#                                              1234          567890123456789012345678901 234567890123456789012345678901234567
               self.send_aprs_msg(sourcetrunc, timestrtxt + " ERROR:Use 8-digit Thuraya \# after SAT. Example:SAT 44441234. " )
               return
           if satargs2.split(' ',1)[1] == "" :
               logger.info("Error validating satellite message number from %s to %s: Blank msg", sourcetrunc,satnum)
#                                               1234567890123456789012345678901234567890123456789012345678901234567
               self.send_aprs_msg(sourcetrunc, timestrtxt + " ERROR:Message body is blank. Include msg after number." )
               return
#           else:
           satmesg = satargs2.split(' ',1)[1]
           cmd = "curl -X POST https://sms.thuraya.com/sms.php -H \"Content-Type: application/x-www-form-urlencoded\" -d \"msisdn=" + satnum + "&from=" + sourcetrunc + "&message=" + satmesg + " -via aprsph.net\""
           try:
               os.system(cmd)
#                                               1234567890123456789012345678901234567890123456789012345678901234567
               self.send_aprs_msg(sourcetrunc, "Attempt send sat SMS to " + satnum + ":" + satmesg[0:30] + "..." )
               logger.info("Sending satellite message from %s to %s: %s", sourcetrunc, satnum, satmesg)
           except:
               self.send_aprs_msg(sourcetrunc, "Error sending sat SMS to " + satnum + ":" + satmesg[0:30] + "..."  )
               logger.info("Error sending satellite message from %s to %s:%s", sourcetrunc,satnum,satmesg)
           with open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc, 'w') as g:
               lasttext = args
               g.write(dupecheck)
               logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)



# START ?APRSM or MESSAGE retrieval from aprs.fi. This feature uses the API to retrieve the last 10 messages and delivers to the user.
# May be useful for checking for any missed messages.


# First we test the output file
        elif qry in ["?aprsm", "?aprsm ", "msg", "msg ", "m", "m ", "?aprsm5", "aprsm10", "aprsm5 ", "aprsm10 ", "msg5", "msg5 ", "msg10", "msg10 ", "m5", "m5 ", "m10", "m10 "] :
# == "?aprsm" or qry == "msg" or qry == "m" or qry == "msg10" or qry == "m10" or qry == "?aprsm10" :
           sourcetrunc = source.replace('*','')
           timestrtxt = time.strftime("%m%d")
# Let's throttle the response to once per 5 minutes. Otherwise, receiving the same query in rapid succession could result in varied sets of responses.
           dupecheck = "/home/pi/ioreth/ioreth/ioreth/aprsm/" + sourcetrunc
           if os.path.isfile(dupecheck) and args =="" :
#                                               1234567890123456789012345678901234567890123456789012345678901234567
               self.send_aprs_msg(sourcetrunc, "?APRSM queries for own callsign+ssid limited to 1x per 30min. " +timestrtxt )
               logger.info("%s already made an ?APRSM query recently. Throttling response.", sourcetrunc)
               return
           if args == "" :
                callsign = sourcetrunc
                with open(dupecheck, 'w') as file:
                     file.write("")
                     logger.info("Adding a dupecheck to throttle responses for %s", sourcetrunc)

# .split('-', 1).upper()
           else:
                callsign = args.split(' ', 1)[0].upper()
           apicall = "https://api.aprs.fi/api/get?what=msg&dst=" + callsign + "&apikey=" +  aprsfiapi + "&format=json"
#           jsonoutput = "/home/pi/ioreth/ioreth/ioreth/aprsm/" + sourcetrunc + ".json"
#           msgoutput = "/home/pi/ioreth/ioreth/ioreth/aprsm/" + sourcetrunc + ".txt"
#           cmd = "wget \"" + apicall + "\" -O " + jsonoutput
           try:
#               hdr = { 'User-Agent' : 'Ioreth APRSPH bot (aprsph.net)' }
#               req = urllib.request.Request(apicall, headers=hdr, timeout=2)
#               response = urllib.request.urlopen(req).read().decode('UTF-8')
#               hdr = "'user-agent': 'APRSPH/2023-01-28b (+https://aprsph.net)'"
               hdr = { 'User-Agent': 'Ioreth APRSPH bot (https://aprsph.net)' }
#               response = urllib.request.urlopen(apicall, timeout=2).read().decode('UTF-8')
               req = urllib.request.Request(url=apicall, headers={'User-Agent':' APRSPH/2023-01-29 (+https://aprsph.net)'})
# Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'})
               response = urllib.request.urlopen(req, timeout=5).read().decode('UTF-8')
#               response = urllib.request.urlopen(apicall, timeout=2).read().decode('UTF-8')
#               response.add_header('User-Agent','APRSPH/2023-01-28 (+https://aprsph.net)')
               jsonResponse = json.loads(response)

           except:
               self.send_aprs_msg(sourcetrunc, "Error in internet or connection to aprs.fi.")
#               logger.info("%s", response)
#               logger.info("%s", jsonResponse)

               logger.info("Internet error in retrieving messages for %s", callsign)
               return

           if jsonResponse['found'] == 0:
                   self.send_aprs_msg(sourcetrunc, "No recent msgs for " + callsign + " or old data was purged.")
                   logger.info("No messages retrieved for %s", callsign)
                   return
           else:
#                   logger.info("%s", response)
#                   logger.info("%s", jsonResponse)
                   timestrtxt = time.strftime("%m%d %H%MZ")

                   count = 0
                   for rows in jsonResponse['entries']:
#                         logger.info("%s", rows)
# Uncomment below to limit ?aprsm output to 5 messages and ?aprsm10 to 10. Otherwise, it generates 10 by default.
                         if count == 5 and qry in ["m5", "msg5", "?aprsm5", "m5 ", "msg5 ", "?aprsm5 "] :
# == "m" or qry == "msg" or qry == "?aprsm" :
                            break
                         count += 1
                         msgtime = datetime.fromtimestamp(int(rows['time'])).strftime('%m-%d %H%MZ')
                         msgsender = rows['srccall']
                         msgmsg = rows['message']
                         strcount = str(count)
                         msgbody = strcount + "." + msgtime + " " + msgsender + ":" + msgmsg
                         if len(msgbody) > 67 :
                            msgbody1 = msgbody[0:61]
                            msgbody2 = msgbody[61:]
                            self.send_aprs_msg(sourcetrunc, msgbody1 + "+" )
                            self.send_aprs_msg(sourcetrunc, strcount + ".+" + msgbody2 )
                         else:
                            self.send_aprs_msg(sourcetrunc, msgbody )

#                         self.send_aprs_msg(sourcetrunc, str(count) + ".From " + msgsender + " sent on " + msgtime )
#                         self.send_aprs_msg(sourcetrunc, str(count) + "." + msgmsg )
#                                                              123456789012345678901234567       8901234567890123456789012345678901234567
                   self.send_aprs_msg(sourcetrunc, str(count) + " latest msgs to " + callsign + " retrieved from aprs.fi on " + timestrtxt )
                   logger.info("Sending last messages retrieved for %s", callsign)

# Deprecated code below. You might want to refer to it in future for other functions.
#           try:
#              os.system(cmd)
#              logger.info("Retrieved last messages for %s", sourcetrunc)
#           except:
#              logger.info("ERROR retrieving last messages from aprs.fi")
#              self.send_aprs_msg(sourcetrunc, "Error retrieving latest msgs from aprs.fi. Try again later.")
#              return

# Now we parse the file
#           with open(jsonoutput, 'r') as file:
#                messages = json.load(file)
#           with open(msgoutput, 'w') as msgfile:
#                for rows in messages:


#                time1 = datetime.datetime.fromtimestamp(int(messages['entries'][0]["time"])).strftime('%Y-%m-%d %H:%M:%S UTC')
#                time2 = datetime.datetime.fromtimestamp(int(messages['entries'][1]["time"])).strftime('%Y-%m-%d %H:%M:%S UTC')
#                time3 = datetime.datetime.fromtimestamp(int(messages['entries'][2]["time"])).strftime('%Y-%m-%d %H:%M:%S UTC')
#                time4 = datetime.datetime.fromtimestamp(int(messages['entries'][3]["time"])).strftime('%Y-%m-%d %H:%M:%S UTC')
#                time5 = datetime.datetime.fromtimestamp(int(messages['entries'][4]["time"])).strftime('%Y-%m-%d %H:%M:%S UTC')
#                sender1 = messages['entries'][0]["srccall"]
#                sender2 = messages['entries'][1]["srccall"]
#                sender3 = messages['entries'][2]["srccall"]
#                sender4 = messages['entries'][3]["srccall"]
#                sender5 = messages['entries'][4]["srccall"]
#                msg1 = messages['entries'][0]["message"]
#                msg2 = messages['entries'][1]["message"]
#                msg3 = messages['entries'][2]["message"]
#                msg4 = messages['entries'][3]["message"]
#                msg5 = messages['entries'][4]["message"]

#                msgfile.write("1.Msg from " + sender1 + " sent on " + time1 + "\n")
#                msgfile.write("1." + msg1 + "\n")
#                msgfile.write("2.Msg from " + sender2 + " sent on " + time2 + "\n")
#                msgfile.write("2." + msg2 + "\n")
#                msgfile.write("3.Msg from " + sender3 + " sent on " + time3 + "\n")
#                msgfile.write("3." + msg3 + "\n")
#                msgfile.write("4.Msg from " + sender4 + " sent on " + time4 + "\n")
#                msgfile.write("4." + msg4 + "\n")
#                msgfile.write("5.Msg from " + sender5 + " sent on " + time5 + "\n")
#                msgfile.write("5." + msg5)
#                msgfile.close()
#                logger.info("Saved message file for %s", sourcetrunc)

# Now we return the list of messages retrieved from APRS.fi
#                self.send_aprs_msg(sourcetrunc, "Last 5 messages to " + sourcetrunc + " retrieved from aprs.fi." )
#                with open(msgoutput, 'r') as msgfile:
#                    lines = msgfile.readlines()
#                    msgfile.close()
#                                                1234567890123456789012345678901234567890123456789012345678901234567

#                    count = 0
#                    for line in lines:
#                          linetrunc = line.replace('\n','')
#                          if linetrunc == "":
#                             self.send_aprs_msg(sourcetrunc, "No recent msgs to display, or old data has been purged.")
#                             logger.info("Nomessages retrieved for %s", sourcetrunc)
#                             return
#                          count +=1
#                          self.send_aprs_msg(sourcetrunc, linetrunc[0:67])
#                    logger.info("Sending last 5 aprs-is messages retrieved for %s", sourcetrunc)

#                msgfile.write("6." + messages['entries'][5]["srccall"] + ":" + messages['entries'][5]["message"] + "\n")
#                msgfile.write("7." + messages['entries'][6]["srccall"] + ":" + messages['entries'][6]["message"] + "\n")
#                msgfile.write("8." + messages['entries'][7]["srccall"] + ":" + messages['entries'][7]["message"] + "\n")
#                msgfile.write("9." + messages['entries'][8]["srccall"] + ":" + messages['entries'][8]["message"] + "\n")
#                msgfile.write("10." + messages['entries'][9]["srccall"] + messages['entries'][9]["message"] + "\n")
#                msgfile.write("\n")

# START ERIC
# This below is an experimental feature for incident command. It's based on the CQ portion of the code, but basically does these:
# 1. Adds the message to an incident command draft.
# 2. Lets the sender add more messages to the draft.
# 3. Lets the sender push the message to a web log.
# 4. Sends the message to stations identified as incident commanders


        elif qry == "ichelp" :
           sourcetrunc = source.replace('*','')
           self.send_aprs_msg(sourcetrunc, "IC[space]msg to start report.ICLAST,ICLATEST for last reports.")
           logger.info("Sending IC help message to %s", sourcetrunc)

        elif qry == "ic" :
           sourcetrunc = source.replace('*','')
           cqnet = 0
# Checking if duplicate message
           dupecheck = qry + " " + args
           if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc) and dupecheck == open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc).read():
                  logger.info("Message is exact duplicate, stop logging" )
                  return
           else:
                  logger.info("Message is not exact duplicate, now logging" )
                  icdraft = '/home/pi/ioreth/ioreth/ioreth/eric/draft/' + sourcetrunc
                  if not os.path.isfile(icdraft):
                       draftmsg = open(icdraft, 'w')
                       with open(icdraft, 'a') as draftmsg:
                         data8 = "Incident Report from {} started on {}\n".format(sourcetrunc,time.strftime("%Y-%m-%d %H:%M:%S %Z"))
                         draftmsg.write(data8)
#                         data9 = "{}:{}\n".format(time.strftime("%H:%M:%S"), args)
#                         draftmsg.write(data9)
                         logger.info("Created and writing %s draft IC file", sourcetrunc)
                  with open(icdraft, 'a') as cqm:
                         data9 = "{}:{}\n".format(time.strftime("%H:%M:%S"), args)
#                         data9 = "{}\n".args
                         cqm.write(data9)
                         logger.info("Writing %s IC message to eric", sourcetrunc)
                         cqm.close

# Record the message somewhere to check if next message is dupe
           with open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc, 'w') as g:
                dupecheck = qry + " " + args
#                lasttext = args
                g.write(dupecheck)
                logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)

# Advise sender their message is logged
           self.send_aprs_msg(sourcetrunc, "RR:" + args[0:24] + ".IC[spc]msg to add.ICPUB to post or ICANCEL.")
           logger.info("Advising %s of message %s being logged", sourcetrunc, args)

# This part lets us push to the web.

        elif qry == "icancel":
           sourcetrunc = source.replace('*','')
           icdraft = '/home/pi/ioreth/ioreth/ioreth/eric/draft/' + sourcetrunc
           if os.path.isfile(icdraft):
              os.remove(icdraft)
              self.send_aprs_msg(sourcetrunc, "Report deleted. IC [space] msg to start new.")
           if not os.path.isfile(icdraft):
              self.send_aprs_msg(sourcetrunc, "No report to delete. IC [space] msg to start new.")

        elif qry == "icpub":
           sourcetrunc = source.replace('*','')
           icdraft = '/home/pi/ioreth/ioreth/ioreth/eric/draft/' + sourcetrunc
           if not os.path.isfile(icdraft):
              self.send_aprs_msg(sourcetrunc, "No report to publish. IC [space] msg to start new.")
           if os.path.isfile(icdraft):
              file = open(icdraft, 'r')
              readdraft = file.read()
              file.close()
              fout = open(iclog, 'a')
              fout.write(readdraft)
              repsubmitted = "Incident Report submitted by {} on {}".format(sourcetrunc, time.strftime("%Y-%m-%d %H:%M:%S %Z"))
              fout.write(repsubmitted)
              fout.write("\n\n")
              fout.close()
              logger.info("Copying report from %s into the main IC log.", sourcetrunc)
              iclasts = iclast + "/" + sourcetrunc
              flast = open(iclasts, 'w')
              flast.write(readdraft)
              flast.write(repsubmitted)
#              flast.write("\n\n")
              flast.close()
              copylatest = "cp " + iclasts + " " + iclatest
              os.system(copylatest)
              os.remove(icdraft)
              logger.info("Copied draft to iclatest and deleting draft report from %s", sourcetrunc)
#              cmd = 'scp /home/pi/ioreth/ioreth/ioreth/eric/eric root@radio1.dx1arm.net:/var/www/aprsph.net/public_html/ic/index.html'
              cmd = 'scp -P 2202 /home/pi/ioreth/ioreth/ioreth/eric/eric root@irisusers.com:/var/www/html/ic/index.html'
              try:
                 os.system(cmd)
                 logger.info("Uploading iclog to the web")
                 self.send_aprs_msg(sourcetrunc, "Published the log messages to web.")
              except:
                 logger.info("ERROR uloading iclog to the web")
                 self.send_aprs_msg(sourcetrunc, "Error in publishing the log messages to web.")
# Send the message to all on the IC list.
              lines = []
              sourcetrunc = source.replace('*','')
              with open(iclist) as sendlist:
                 lines = sendlist.readlines()
              count = 0
              for line in lines:
                 linetrunc = line.replace('\n','')
                 count += 1
                 with open(iclasts) as sendlast:
                     lineslast = sendlast.readlines()
                 countlast = 0
                 for linelast in lineslast:
                     countlast += 1
                     linelasttrunc = linelast.replace('\n','')
                     self.send_aprs_msg(linetrunc,linelasttrunc[9:])
              logger.info("Sending IC message to %s", linelasttrunc)
# We will attempt to send an email
              lines = []
              with open(iclasts) as reportsubject:
                  reportsubj = reportsubject.readlines()[-1]
              icmailcmd = "cat " + iclasts + " | /home/pi/ioreth/ioreth/ioreth/eric/patmail.sh jangelo@gmail.com \"" + reportsubj + "\" telnet" 
              try:
                  os.system(icmailcmd)
                  self.send_aprs_msg(sourcetrunc, "Emailed " + reportsubj[9:])
                  logger.info("Sending IC message to email") 
              except:
                  self.send_aprs_msg(sourcetrunc, "IC email error.")
                  logger.info("Error sending IC message to email") 

# For below, just email and not send/publish to all
        elif qry == "icmail":
              iclasts = iclast + "/" + sourcetrunc
              lines = []
              if not os.path.isfile(iclasts):
                  self.send_aprs_msg(sourcetrunc, "No report to email. IC [space] message to start new report.")
                  logger.info("No report to email") 
                  return
              with open(iclasts) as reportsubject:
                  reportsubj = reportsubject.readlines()[-1]
              icmailcmd = "cat " + iclasts + " | /home/pi/ioreth/ioreth/ioreth/eric/patmail.sh jangelo@gmail.com \"" + reportsubj + "\" telnet" 
              try:
                  os.system(icmailcmd)
                  self.send_aprs_msg(sourcetrunc, "Emailed " + reportsubj[9:])
                  logger.info("Sending IC message to email") 
              except:
                  self.send_aprs_msg(sourcetrunc, "IC email error.")
                  logger.info("Error sending IC message to email") 

#              icfile = open(iclast, 'r')
#              iclastread = icfile.read()

#              cmd1 = "curl http://raspberrypi.local:8080/api/mailbox/out -F 'date=$(date -u +'%Y-%m-%dT%H:%M:%SZ')' -F 'to=4I1RAC' -F 'subject=Incident report from " + sourcetrunc + "' -F 'body='" + iclastread + "'"
#              os.system(cmd1)
#              import requests

#              files = {
#                      'date': (None, '$(date -u +\'%Y-%m-%dT%H:%M:%SZ\')'),
#                      'subject': (None, 'Hello ma'),
#                      'to': (None, '4I1RAC'),
#                      'body': (None, 'test'),
#                      }

#              response = requests.post('http://raspberrypi.local:8080/api/mailbox/out', files=files)

#              headers = {
#                        'Content-Type': 'application/x-www-form-urlencoded',
#                        }
#
#              with open('/home/pi/ioreth/ioreth/ioreth/eric/iclast') as f:
#                        data = f.readline().strip('\n')
#
#              response = requests.post('http://raspberrypi.local:8080/api/mailbox/out', headers=headers, data=data)
#              logger.info("Attempting to send IC message by email")

# Send the message to all on the IC list.
#           lines = []
#           sourcetrunc = source.replace('*','')
#           with open(iclist) as sendlist:
#                lines = sendlist.readlines()
#           count = 0
#           for line in lines:
#                linetrunc = line.replace('\n','')
#                count += 1
#                self.send_aprs_msg(linetrunc, sourcetrunc + ">" + args)
#           logger.info("Sending IC message to %s except %s", linetrunc, sourcetrunc)




        elif qry == "iclast":
# Retrieve the last report
              lineslast = []
              sourcetrunc = source.replace('*','')
              iclasts = iclast + "/" + sourcetrunc
              if not os.path.isfile(iclasts):
                  self.send_aprs_msg(sourcetrunc,"No report to retrieve for " + sourcetrunc)
                  logger.info("No IC report to retrieve for %s.", sourcetrunc)
                  return
              with open(iclasts) as sendlast:
                  lineslast = sendlast.readlines()
              countlast = 0
              for linelast in lineslast:
                  countlast += 1
                  linelasttrunc = linelast.replace('\n','')
                  self.send_aprs_msg(sourcetrunc,str(countlast) + "." + linelasttrunc[9:])
              logger.info("Sending lst IC report to %s.", sourcetrunc)

        elif qry == "iclatest":
# Retrieve the last report from anyone
              lineslast = []
              sourcetrunc = source.replace('*','')
              with open(iclatest) as sendlast:
                  lineslast = sendlast.readlines()
              countlast = 0
              for linelast in lineslast:
                  countlast += 1
                  linelasttrunc = linelast.replace('\n','')
                  self.send_aprs_msg(sourcetrunc,str(countlast) + "." + linelasttrunc[9:])
              logger.info("Sending latest IC report to %s.", sourcetrunc)




# This part allows user to retrieve the IC log

        elif qry == "iclog":
             with open(iclog) as netlast:
                  lasts = netlast.readlines()
                  lastlines = lasts[-10:]
                  netlast.close()
             count = 0
             for line in lastlines:
                  count += 1
                  self.send_aprs_msg(sourcetrunc, str(count) + "." + line[9:] )
             logger.info("Sending last 10 IC messages to  %s", sourcetrunc)
             self.send_aprs_msg(sourcetrunc, "Last 10 IC messages received.")

        elif qry == "iclog2":
             with open(iclog) as netlast:
                  lasts = netlast.readlines()
                  lastlines = lasts[-21:-11]
                  netlast.close()
             count = 0
             for line in lastlines:
                  count += 1
                  self.send_aprs_msg(sourcetrunc, str(count) + "." + line[9:] )
             logger.info("Sending 10 out of last 20 IC messages to  %s", sourcetrunc)
             self.send_aprs_msg(sourcetrunc, "10 of last 20 IC mesge received.")

        elif qry == "iclog3":
             with open(iclog) as netlast:
                  lasts = netlast.readlines()
                  lastlines = lasts[-31:-21]
                  netlast.close()
             count = 0
             for line in lastlines:
                  count += 1
                  self.send_aprs_msg(sourcetrunc, str(count) + "." + line[9:] )
             logger.info("Sending 10 out of last 30 IC messages to  %s", sourcetrunc)
             self.send_aprs_msg(sourcetrunc, "10 of last 30 IC mesge received.")


# END ERIC




# This is for permanent subscribers in your QST list. 
# Basically a fixed implementation of "CQ" but with subscribers not having any control.
# Good for tactical uses, such as RF-only or off-grid environments.

        elif qry == "qst":
             sourcetrunc = source.replace('*','')
             lines = []
             with open(dusubs) as f:
                  lines = f.readlines()
             count = 0
             for line in lines:
                  count += 1
#                  mespre = (line[1:4])
                  self.send_aprs_msg(line.replace('\n',''), sourcetrunc + "/" + args )
                  logger.info("Sending QST message to %s", line)
             file = open(dusubslist, 'r')
             data21 = file.read()  
             data2 = data21.replace('\n','')
             file.close()
             self.send_aprs_msg(source, "Sent msg to QST recipients. Ask DU2XXR for list." )
             logger.info("Advising %s of messages sent to %s", sourcetrunc, data2)
#             file.close()

# Lines below let the user retrieve the last messages from the log.
        elif qry in ["last", "log", "last5", "last10", "log10", "last15", "log15", "mine", "mine10", "mine15", "search", "mine ", "mine10 ", "mine15" ] :
#        elif qry == "last" or qry == "log" or qry == "last5" or qry == "last10" or qry == "log10" or  qry == "last15" or qry == "log15" or qry == "mine" or qry == "mine10" or qry == "mine15" or qry == "search" :
             sourcetrunc = source.replace('*','')
             timestrtxt = time.strftime("%m%d")
#             callnossid = sourcetrunc.split('-', 1)[0]
             if qry in ["mine", "mine ", "mine5", "mine5 ", "mine10", "mine10 "] :
#             if qry == "mine" or qry == "mine10" or qry == "mine15" :
                  filename2 = "/home/pi/ioreth/ioreth/ioreth/lastforme"
                  if not args == "" or not args == " " :
                     callsigns = args.split(' ', 1)[0].upper()
                     cmd1 = "cat /home/pi/ioreth/ioreth/ioreth/archive/index.html | grep -i \"" + callsigns + ":\" -a --text >/home/pi/ioreth/ioreth/ioreth/lastforme"
                     cmd2 = "; cat /home/pi/ioreth/ioreth/ioreth/netlog-msg | grep -i \"" + callsigns + ":\" -a --text >>/home/pi/ioreth/ioreth/ioreth/lastforme"
                     cmd = cmd1 + cmd2
                  if args.upper() == "THURS" or args.upper() == "THURSDAY" or args.upper() == "APRSTHURSDAY" or args.upper() == "#APRSTHURSDAY" :
#                     filename2 = "/home/pi/ioreth/ioreth/ioreth/aprsthursday/index.html"
                     callsigns = sourcetrunc.upper()
                     cmd1 = "cat /home/pi/ioreth/ioreth/ioreth/aprsthursday/archives/index.html | grep -i \"" + callsigns + ":\" -a --text >/home/pi/ioreth/ioreth/ioreth/lastforme"
                     cmd2 = " ; cat /home/pi/ioreth/ioreth/ioreth/aprsthursday/index.html | grep -i \"" + callsigns + ":\" -a --text >>/home/pi/ioreth/ioreth/ioreth/lastforme"
                     cmd = cmd1 + cmd2
#                  else:
                  if args == "" or args == " " :
                     callsigns = sourcetrunc.upper()
                     cmd1 = "cat /home/pi/ioreth/ioreth/ioreth/archive/index.html | grep -i \"" + callsigns + ":\" -a --text >/home/pi/ioreth/ioreth/ioreth/lastforme"
                     cmd2 = "; cat /home/pi/ioreth/ioreth/ioreth/netlog-msg | grep -i \"" + callsigns + ":\" -a --text >>/home/pi/ioreth/ioreth/ioreth/lastforme"
                     cmd = cmd1 + cmd2
                  os.system(cmd)


             elif qry == "search" or qry == "search10" or qry == "search15" :
                  filename2 = "/home/pi/ioreth/ioreth/ioreth/search"
                  timestrtxt = time.strftime("%m%d")
                  if args == "" :
#                                                     1234567890123456789012345678901234567890123456789012345678901234567
                     self.send_aprs_msg(sourcetrunc, timestrtxt + " ERROR:Include a search string after SEARCH." )
                     return
                  else:
                     cmd1 = "cat /home/pi/ioreth/ioreth/ioreth/archive/index.html | grep -i \"" + args + "\" -a --text >/home/pi/ioreth/ioreth/ioreth/search"
                     cmd2 = "; cat /home/pi/ioreth/ioreth/ioreth/netlog-msg | grep -i \"" + args + "\" -a --text >>/home/pi/ioreth/ioreth/ioreth/search"
                     cmd = cmd1 + cmd2
                     os.system(cmd)
#             elif args.upper() == "THURS" or args.upper() == "THURSDAY" or args.upper() == "APRSTHURSDAY" or args.upper() == "#APRSTHURSDAY" :
             elif args.upper() in ["THURS", "THURS ", "THURSDAY", "THURSDAY ", "APRSTHURSDAY", "APRSTHURSDAY ", "#APRSTHURSDAY", "#APRSTHURSDAY "] :
                  filename2 = "home/pi/ioreth/ioreth/ioreth/aprsthursday/index.html"
             else: 
                  filename2 = "home/pi/ioreth/ioreth/ioreth/netlog-msg"
             with open(filename2) as netlast:
                  lasts = netlast.readlines()
                  lastlines = lasts[-5:]
                  if qry == "last10" or qry == "log10" or qry == "mine10" or qry == "search10" : 
                        lastlines = lasts[-10:]
                  if qry == "last15" or qry == "log15" or qry == "mine15" or qry == "search15" : 
                        lastlines = lasts[-15:]
                  netlast.close()
#                                                  1234567890123456789012345678901234567890123456789012345678901234567
             if qry == "mine" or qry == "mine10" or qry == "mine15" :
                  timestrtxt = time.strftime("%m%d %H%MZ")
                  if len(lastlines) < 1 :
                       self.send_aprs_msg(sourcetrunc, timestrtxt +":No results for " + callsigns + ". Try a different one or HELP." )
#                  elif args.upper() == "THURS" or args.upper() == "THURSDAY" or args.upper() == "APRSTHURSDAY" or args.upper() == "#APRSTHURSDAY" :
                  elif args.upper() in ["THURS", "THURS ", "THURSDAY", "THURSDAY ", "APRSTHURSDAY", "APRSTHURSDAY ", "#APRSTHURSDAY", "#APRSTHURSDAY "] :

                       self.send_aprs_msg(sourcetrunc, "Last #APRSThursday msgs from " + callsigns + " retrieved " + timestrtxt )
                  else: 
                       self.send_aprs_msg(sourcetrunc, "Last NET/CQ messages by " + callsigns + ". More info: aprsph.net" )
             if qry == "search" or qry == "search10" or qry == "search15" :
                  timestrtxt = time.strftime("%m%d %H%MZ")
                  if len(lastlines) < 1 :
                       self.send_aprs_msg(sourcetrunc, timestrtxt + ":No results for " + args +"." )
                  else: 
                       self.send_aprs_msg(sourcetrunc, timestrtxt + ":Msgs with \"" + args + "\"" )
# CQ[space]msg reply,LIST for recipients,HELP cmds. Info:aprsph.net" )
             if args.upper() in ["THURS", "THURS ", "THURSDAY", "THURSDAY ", "APRSTHURSDAY", "APRSTHURSDAY ", "#APRSTHURSDAY", "#APRSTHURSDAY "] :
                if qry in ["laast", "last10", "last15"]  :
#                                                  1234567890123456789012345678901234567890123456789012345678901234567
                  timestrtxt = time.strftime("%m%d %H%MZ")
                  self.send_aprs_msg(sourcetrunc, "Last #APRSThursday messages. Info: https://aprsph.net " + timestrtxt )
             else :
                  self.send_aprs_msg(sourcetrunc, "CQ[spc]msg reply,LIST recipients,HELP cmds.Info:aprsph.net " + timestrtxt )

             count = 0
             for line in lastlines:
                  count += 1
                  strcount = str(count)
                  msgdate = line[5:11]
                  msgtime = line[11:16].replace(':','') + "Z "
                  msgcontent = line[24:]
                  msgbody = msgdate + msgtime + msgcontent
                  msgbodywithcount = strcount + "."  + msgbody
                  if not line[0:3] == "202" :
                      count -= 1
# If it is not a log record, do not display
#                      return
                  elif len(msgbodywithcount) > 67 :
                       msgbody1 = msgbody[0:61]
                       msgbody2 = msgbody[61:]
                       self.send_aprs_msg(sourcetrunc, strcount + "." + msgbody1 + "+" )
                       self.send_aprs_msg(sourcetrunc, strcount + ".+" + msgbody2 )
                  else:
                       self.send_aprs_msg(sourcetrunc, msgbodywithcount )
             timestrtxt = time.strftime("%m%d %H%MZ")
             self.send_aprs_msg(sourcetrunc, str(count) + " messages retrieved on " + timestrtxt + ". Info: https://aprsph.net" )
             logger.info("Sending last %s messages to  %s", count, sourcetrunc)


# Let the user set up aliasses for their SMS contacts
        elif qry == "smsalias" or qry == "setalias":
             timestrtxt = time.strftime("%m%d %H%MZ")
             sourcetrunc = source.replace('*','')
             callnossid = sourcetrunc.split('-', 1)[0]
             SMS_DESTINATION = args[0:11]
             SMS_ALIAS = args[12:].replace(' ','')
             aliasscratch = "/home/pi/ioreth/ioreth/ioreth/smsaliasscratch/" + callnossid
             aliasfile = "/home/pi/ioreth/ioreth/ioreth/smsalias/" + callnossid
# stop processing duplicates, since APRS sends messages multiple times.
             if not os.path.isfile(aliasscratch):
                 aliases = open(aliasscratch, 'w')
             if args == open(aliasscratch).read():
                 logger.info("Already processed alias for %s %s recently. No longer processing.", SMS_DESTINATION, SMS_ALIAS)
                 return
             if not args[0:2] == "09" or SMS_DESTINATION.isnumeric() == False :
#                                                 1234567890123456789012345678901234567890123456789012345678901234567
                 self.send_aprs_msg(sourcetrunc, "ERROR: Must be exact number format then alias name." + timestrtxt)
                 self.send_aprs_msg(sourcetrunc, "SMSALIAS 09######### NAME to set.SMS NAME to send once set." +timestrtxt)
                 self.send_aprs_msg(sourcetrunc, "The APRSPH SMS gateway only works with Philippine numbers. " +timestrtxt)
                 return
             if not os.path.isfile(aliasscratch):
                 aliases = open(aliasscratch, 'w')
             with open(aliasscratch, 'w') as makealias:
                 writealias = "{} {}".format(SMS_DESTINATION, SMS_ALIAS)
                 makealias.write(writealias)
             if not os.path.isfile(aliasfile):
                 aliases = open(aliasfile, 'a')
             with open(aliasfile, 'a') as makealias:
                 writealias = "{} {}\n".format(SMS_DESTINATION, SMS_ALIAS)
                 makealias.write(writealias)
                 self.send_aprs_msg(sourcetrunc, "SMS " + SMS_ALIAS + " will now send to " + SMS_DESTINATION)
                 logger.info("Writing alias for sender %s as %s %s", sourcetrunc, SMS_DESTINATION, SMS_ALIAS)

# SMS handling for DU recipients. Note that this requires gammu-smsd daemon running on your local machine, with
# the user having access to the SMS storage directories, as well as an extra folder called "processed" where
# SMS inbox messages are moved once they are processed.
        elif qry == "sms":
          timestrtxt = time.strftime("%m%d %H%MZ")
          sourcetrunc = source.replace('*','')
          callnossid = sourcetrunc.split('-', 1)[0]
          SMS_TEXT = (sourcetrunc + " via APRSPH:\n\n" + args.split(' ', 1)[1] + "\n\n@" + sourcetrunc + " [spc] msg to reply. Radio msgs NOT private! aprsph(dot)net for info" )
# First set the characters after SMS as the initial destination
          SMS_DESTINATION = ""
#          SMS_DESTINATION = args[0:11]
# First check if using alias or not
          aliasfound = []
          aliasfile = "/home/pi/ioreth/ioreth/ioreth/smsalias/" + callnossid
          cellaliasfile = "/home/pi/ioreth/ioreth/ioreth/smsalias/CELLULAR"
          smsoralias = args.split(' ', 1)[0]
          smsoraliasupper = smsoralias.upper()
# Check cellular-initiated aliases first
          with open(cellaliasfile, 'r') as file:
               lines = file.readlines()
          count = 0
          for line in lines:
                          count += 1
                          names = line.replace('\n','')
                          names2 = names[12:]
                          logger.info("Trying to match '%s' with '%s'.", smsoralias, names2.upper() )
                          if smsoraliasupper == names2.upper():
                             SMS_DESTINATION = line[0:11]
                             logger.info("Self-set alias found for %s as %s.", smsoralias, SMS_DESTINATION )

# If Alias file is present, then APRS-initiated alias takes precedence

          if os.path.isfile(aliasfile):
#                SMS_DESTINATION = args[0:11]
#                logger.info("No alias file found, just sending to number." )
#          else:






              logger.info("Callsign's own alias file found, trying to match '%s' to a number.",smsoralias )
              lines = []
              with open(aliasfile, 'r') as file:
                    lines = file.readlines()
              count = 0
              for line in lines:
                          count += 1
                          names = line.replace('\n','')
                          names2 = names[12:]
                          logger.info("Trying to match '%s' with '%s'.", smsoralias, names2.upper() )
                          if smsoraliasupper == names2.upper():
                             SMS_DESTINATION = line[0:11]
                             logger.info("Alias found for %s as %s.", smsoralias, SMS_DESTINATION )

          if SMS_DESTINATION == "":
                SMS_DESTINATION = args[0:11]
                logger.info("No alias file found, just sending to number." )

# establish our SMS message

          sendsms = ( "echo '" + SMS_TEXT + "' | gammu-smsd-inject TEXT " + SMS_DESTINATION )

# Check first if duplicate
          dupecheck = qry + " " + args

          if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/lastmsgsms/' + sourcetrunc) and  dupecheck == open('/home/pi/ioreth/ioreth/ioreth/lastmsgsms/' + sourcetrunc).read():
             logger.info("Received message for SMS that is exact duplicate. Stop sending SMS." )
             return
          else:
             logger.info("Received message for SMS that is not exact duplicate, now sending SMS" )

             if args == "":
                 self.send_aprs_msg(sourcetrunc, "SMS 09XXXXXXXXX msg. PH#s only. SMSALIAS # name to set nicknames." )
                 logger.info("Replying to %s about SMS instructions", sourcetrunc)
                 return


             with open('/home/pi/ioreth/ioreth/ioreth/lastmsgsms/' + sourcetrunc, 'w') as g:
#                   lasttext = args
                   g.write(dupecheck)
                   logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)
             sourcetrunc = source.replace('*','')

# Validating the destination. In the Philippines, cell numbers start with 09XX. Adjust this accordingly.

             if not SMS_DESTINATION[0:2] == "09" or SMS_DESTINATION.isnumeric() == False :
#                                                 1234567890123456789012345678901234567890123456789012345678901234567
                 self.send_aprs_msg(sourcetrunc, "ERROR: Must be exact number format or existing alias. " + timestrtxt)
                 self.send_aprs_msg(sourcetrunc, "SMS NAME Message if existing alias. SMSALIAS to set. " + timestrtxt)
                 self.send_aprs_msg(sourcetrunc, "SMS 09######### Msg if no alias. Philippine #s only. " + timestrtxt)
                 logger.info("Replying to %s that %s is not a valid number.", sourcetrunc, SMS_DESTINATION)
                 return

             try:
#                   os.system(sendsms)
                   self.send_aprs_msg(sourcetrunc, "SMS " + smsoralias + " " + args.split(' ')[1] + " " + args.split(' ')[2] +  "...-sending. Note: APRS msgs not private." )
                   aliasfile = "/home/pi/ioreth/ioreth/ioreth/smsalias/" + callnossid
                   smsoralias = args.split(' ', 1)[0]
                   if not os.path.isfile(aliasfile):
                         self.send_aprs_msg(sourcetrunc, "U may use alias.SMSALIAS 09XXXXXXXXX NAME to set.SMS NAME to send.")
                   logger.info("Replying to %s that SMS to %s is being sent", sourcetrunc, SMS_DESTINATION)
# Let's restart the SMS modem first, because we've been encountering some issues with the modem.
                   restartmodem = "/home/pi/gammu-restart.sh"
                   os.system(restartmodem)
# Now we queue the message.
                   os.system(sendsms)
                   logger.info("Sending SMS from %s to %s", sourcetrunc, SMS_DESTINATION)
             except:
                   self.send_aprs_msg(sourcetrunc, "SMS " + args.split(' ')[1] + " " +  args.split(' ')[2] + "... Could not be sent.")
                   logger.info("Could not send SMS from %s to %s", sourcetrunc, SMS_DESTINATION)

# This is necessary, since APRS messages may be sent or received multiple times (e.g., heard from another digipeater)
# This ensures that the SMS being sent will not be doubled. When the same message is heared on this machine, processing
# Stops already because the message has been queued by Gammu-smsd. Same case with other processes here.

#          else:
#             logger.info("SMS fromm %s to %s is a duplicate. No longer processing", sourcetrunc, SMS_DESTINATION)

        elif qry in random_replies:
            self.send_aprs_msg(sourcetrunc, random_replies[qry] )

        else:
            timestrtxt = time.strftime("%m%d %H%MZ")
#                                                1234567890123456789012345678901234567890123456789012345678901234567
            self.send_aprs_msg(sourcetrunc, timestrtxt + ":Command not found: " + qry.upper() )
#                                                1234567890123456789012345678901234567890123456789012345678901234567
            self.send_aprs_msg(sourcetrunc, timestrtxt + ":CQ [spc] msg to join,LIST,LAST. Info:HELP or aprsph.net" )
            dupecheck = qry + " " + args
            with open('/home/pi/ioreth/ioreth/ioreth/lastmsgdir/' + sourcetrunc, 'w') as g:
                lasttext = args
                g.write(dupecheck)
                logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)

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
# These lines count the number of SMS sent and received
        smsproc = "ls -1 /var/spool/gammu/processed | wc -l > /home/pi/ioreth/ioreth/ioreth/smsrxcount"
        smsrxcount = os.system(smsproc)
        smssent = "ls -1 /var/spool/gammu/sent | wc -l > /home/pi/ioreth/ioreth/ioreth/smstxcount"
        smstxcount = os.system(smssent)
        

        smsrxnum = open('/home/pi/ioreth/ioreth/ioreth/smsrxcount', 'r')
        smsrxcounts = smsrxnum.read()
#        smsrxtotals1 = smsrxcounts.replace('total ','')
        smsrxtotals = smsrxcounts.replace('\n','')
        smsrxnum.close()

        smstxnum = open('/home/pi/ioreth/ioreth/ioreth/smstxcount', 'r')
        smstxcounts = smstxnum.read()
#        smstxtotals1 = smstxcounts.replace('total ','')
        smstxtotals = smstxcounts.replace('\n','')
        smstxnum.close()

# These lines count the number of checkins

        timestr = time.strftime("%Y%m%d")
        filename1 = "/home/pi/ioreth/ioreth/ioreth/netlog-"+timestr
        daylog = open(filename1, 'r')
        dayta2 = daylog.read()
        daylog.close()
        dayta3 = dayta2.replace('\n','')
        count = 0
        for i in dayta3:
                         if i == ',':
                            count = count + 1

        strcount = str(count)

        net_status = (
            self._check_host_scope("Link", "eth_host")
            + self._check_host_scope("YSF", "inet_host")
            + self._check_host_scope("VHF", "dns_host")
            + self._check_host_scope("VPN", "vpn_host")
        )
        self.status_str = "%s checkins.NET join.HELP cmds.SMS T%sR%s DU2XXR" % (
#            time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            strcount,
            smstxtotals,
            smsrxtotals,
#            utils.human_time_interval(utils.get_uptime()),
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
        recon = 'sudo systemctl restart ioreth'
        os.system(recon)


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
            timestrtxt = time.strftime("%m%d")
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

# These lines are for checking if there are SMS messages received. Maybe find a better place for it
# but the bulletins portion of the code might be the best place, as there may be no need to poll
# for new SMS every so often.

        smsinbox = "/var/spool/gammu/inbox/"
        smsfolder = os.listdir(smsinbox)
        smsinbox = "/var/spool/gammu/inbox/"
        smsfolder = os.listdir(smsinbox)
        smsalias = 0
        if len(smsfolder)>0:
            for filename in os.listdir(smsinbox):
                    smsnumber = filename[24:34]
                    smssender = "0"+smsnumber
                    logger.info("Found message in SMS inbox. Now processing.")
                    smsalias = "none"
                    smstxt = open(smsinbox + filename, 'r')
                    smsread = smstxt.read()
                    smsreceived = smsread.replace('\n',' ')
                    smstxt.close()
                    prefix = filename[22:25]
                    smsstart = smsreceived.split(' ',1)[0]
                    smsstartupper = smsstart.upper()
# Ignore if from self
                    if smssender == "09760685303":
                       logger.info("Found message from self. Removing.")
                       movespam = ("sudo rm "+ smsinbox + filename)
                       os.system(movespam)
                       return

                    if not prefix == "639":
                               logger.info("Possibly a carrier message or spam from %s. No longer processing", smssender )
                               movespam = ("sudo mv "+ smsinbox + filename + " /var/spool/gammu/spam")
                               os.system(movespam)
                    else:
# Let cell user create an alias
                      

                      if smsstartupper == "ALIAS":
                          cellaliasfile = "/home/pi/ioreth/ioreth/ioreth/smsalias/CELLULAR"
                          isbodyalias = len(smsreceived.split())
                          if isbodyalias > 1 :
                              cellownalias = smsreceived.split(' ', 1)[1]
                              logger.info("Alias body found. Setting self alias")
                          else:
                              cellownalias = ""
                          aliastext = smssender + " " + cellownalias
                          with open(cellaliasfile, 'a') as makealias:
                              writealias = "{} {}\n".format(smssender, cellownalias)
                              makealias.write(writealias)
                          sendsms = ( "echo 'U have set ur own alias as " + cellownalias + ". Ur # will not appear on msgs. aprsph(.)net for more info.' | gammu-smsd-inject TEXT 0" + smsnumber )
                          os.system(sendsms)
                          logger.info("Self-determined alias set for for %s as %s.", smsnumber, cellownalias )
                      if smsstartupper == "SAT" :
#  or smsstartupper == "SATNASH" or smsstartupper == "SATRAC" : DEPRECATED OLD COMMANDS
                         isbody = len(smsreceived.split())
                         if isbody > 1 :
                              smsbody = smsreceived.split(' ', 1)[1]
                              logger.info("Message body found. Sending message")
                         else:
                              smsbody = "EMPTY MSG BODY"
                              sendsms = ( "echo 'ERROR: Format is SMS ######## Message, where # are the 8-digit Thuraya number.  More info at aprsph dot net.' | gammu-smsd-inject TEXT 0" + smsnumber )
                              os.system(sendsms)
                              logger.info("Message body not found. Replying to %s with error message.",smsnumber)
                              return
                         satargs = smsbody.replace('\"','')
                         satargs2 = satargs.replace('\'','')
                         satnumber = satargs2.split(' ',1)[0]
                         satmesg = satargs2.split(' ',1)[1]
                         satmesgtrunc = satmesg[0:138]
                         if not len(satnumber) == 8 or satnumber.isnumeric() == False  :
                            logger.info("Error validating satellite message number from %s to %s:%s", smssender,satnumber,satmesgtrunc)
                            sendsms = ( "echo 'ERROR: Include 8-digit Thuraya number after SAT. Example: SAT 44441212 Message here. Info at aprsph dot net' | gammu-smsd-inject TEXT 0" + smsnumber )
                            os.system(sendsms)
                            movecmd = ("sudo mv "+ smsinbox + filename + " /var/spool/gammu/processed")
                            os.system(movecmd)
                            logger.info("Cleaning up SMS inbox.")


                            return

                         sendsms = ( "echo 'Attempting to send satphone SMS to " + satnumber + " More info at aprsph dot net.' | gammu-smsd-inject TEXT 0" + smsnumber )
                         cmd = "curl -X POST https://sms.thuraya.com/sms.php -H \"Content-Type: application/x-www-form-urlencoded\" -d \"msisdn=" + satnumber + "&from=" + smssender + "&message=" + satmesgtrunc + " -via aprsph.net\""
                         try:
                            os.system(cmd)
                            os.system(sendsms)
                            logger.info("Attempting send satellite message from %s to %s:%s", smssender,satnumber,satmesgtrunc)
                         except:
                            sendsms = ( "echo 'Error sending satphone SMS to " + satnum+ ". Pls try again later. More info at aprsph dot net' | gammu-smsd-inject TEXT 0" + smsnumber )
                            os.system(sendsms)
                            logger.info("Error sending satellite message from %s to %s:%s", smssender,satnumber,satmesgtrunc)
#                         return
# Let's restart the SMS modem first, because we've been encountering some issues with the modem.
                         restartmodem = "/home/pi/gammu-restart.sh"
                         os.system(restartmodem)
                         movecmd = ("sudo mv "+ smsinbox + filename + " /var/spool/gammu/processed")
                         os.system(movecmd)
                         logger.info("Cleaning up SMS inbox.")



                      elif smsreceived[0:1] == "@":
                          callsig = smsreceived.split(' ', 1)[0]
                          callsign = callsig.upper()
                          callnossid = callsign.split('-', 1)[0]
                          isbody = len(smsreceived.split())
                          if isbody > 1 :
                              smsbody = smsreceived.split(' ', 1)[1]
                              logger.info("Message body found. Sending message")
                          else:
                              smsbody = "EMPTY MSG BODY"
                              logger.info("Message body not found. Sending empty")
# Let's check if the sender has an alias, and if so we use that instead of the number for privacy.
                          aliaspath = "/home/pi/ioreth/ioreth/ioreth/smsalias/"
                          aliascheck = aliaspath + callnossid[1:]
                          cellaliascheck = aliaspath + "CELLULAR"
# Let's check if the sender has a self-assigned alias
                          lines = []
                          cellsmsalias = 0
                          with open(cellaliascheck, 'r') as file:
                              lines = file.readlines()
                          count = 0
                          for line in lines:
                              count += 1
                              names = line.replace('\n','')
                              alias = names[12:]
                              logger.info("Trying to match '%s' with '%s'.", smsnumber, names )
                              if smsnumber == names[1:11]:
                                    smssender = alias
                                    cellsmsalias = 1
                                    logger.info("Self-determined alias found for %s as %s.", smsnumber, alias )
# But, the CALLSIGN's own alias file takes precedence over self-determined aliases, so check this also.
                          if not os.path.isfile(aliascheck):
#                               smssender = "0" + smsnumber
                               logger.info("No alias file found at %s%s, using SMS-defined alias or number.", aliaspath, callnossid[1:] )
                               smsalias = 0
                          else:
                               logger.info("Alias file found, trying to match '%s' to an alias.",smsnumber )
                               lines = []
                               with open(aliascheck, 'r') as file:
                                  lines = file.readlines()
                               count = 0
                               for line in lines:
                                   count += 1
                                   names = line.replace('\n','')
                                   alias = names[12:]
                                   logger.info("Trying to match '%s' with '%s'.", smsnumber, names )
                                   if smsnumber == names[1:11]:
                                         smssender = alias
                                         smsalias = 1
                                         logger.info("Alias found for %s as %s.", smsnumber, alias )
# Now send  the message. Split it if too long.
                          if len(smsbody) > 50:
                               smsbody1 = smsbody[0:47]
                               smsbody2 = smsbody[47:110]
                               smsbody3 = smsbody[110:173]
                               smsbody4 = smsbody[173:]
                               if len(smsbody) >= 48 and len(smsbody) <= 110:
                                  self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender + " 1/2:" + smsbody1)
                                  self._aprs.send_aprs_msg(callsign[1:], "2/2:" + smsbody2)
                                  self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender + " Message to send/reply to PH SMS.")
                                  logger.info("SMS too long to fit 1 APRS message. Splitting into 2.")
                               if len(smsbody) >= 111 and len(smsbody) <= 173:
                                  self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender + " 1/3:" + smsbody1)
                                  self._aprs.send_aprs_msg(callsign[1:], "2/3:" + smsbody2)
                                  self._aprs.send_aprs_msg(callsign[1:], "3/3:" + smsbody3)
                                  self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender + " Message to send/reply to PH SMS.")
                                  logger.info("SMS too long to fit 1 APRS message. Splitting into 3.")
                               if len(smsbody) >= 173:
                                  self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender + " 1/4:" + smsbody1)
                                  self._aprs.send_aprs_msg(callsign[1:], "2/4:" + smsbody2)
                                  self._aprs.send_aprs_msg(callsign[1:], "3/4:" + smsbody3)
                                  self._aprs.send_aprs_msg(callsign[1:], "4/4:" + smsbody4)
                                  self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender + " Message to send/reply to PH SMS.")
                                  logger.info("SMS too long to fit 1 APRS message. Splitting into 4.")
                          else:
                               self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender + ":" + smsbody)
                               self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender + " Message to send/reply to PH SMS.")
                               logger.info("SMS is in correct format. Sending to %s.", callsign)
                          if smsalias == 1 or cellsmsalias == 1:
                               sendsms = ( "echo 'APRS msg to " + callsign[1:] + " has been sent. APRS msgs not private, but ur # has an alias & will not appear. APRSPH(dot)net for info.' | gammu-smsd-inject TEXT 0" + smsnumber )
                          else:
                               sendsms = ( "echo 'APRS msg to " + callsign[1:] + " sent. Ur # & msg may appear on online services. Send ALIAS yourname to set an alias. Go aprsph(dot)net for info.' | gammu-smsd-inject TEXT 0" + smsnumber )
                          logger.info("Sending %s a confirmation message that APRS message has been sent.", smssender)
                          os.system(sendsms)
                      else:
#                          if smsalias == 1:
                          sendsms = ( "echo 'To text APRS user: \n\n@CALSGN-SSID Message\n\nMust hv @ b4 CS (SSID optional if none). To set ur alias & mask ur cell#:\n\nALIAS myname\n\naprsph . net for info.' | gammu-smsd-inject TEXT 0" + smsnumber )
#                          else:
#                                sendsms = ( "echo 'Incorrect format.Use: \n\n@CALSGN-SSID Message\n\nto text APRS user. Must have @ before CS. 1/2-digit SSID optional if none.' | gammu-smsd-inject TEXT 0" + smsnumber )


                          os.system(sendsms)
                    movecmd = ("sudo mv "+ smsinbox + filename + " /var/spool/gammu/processed")
                    os.system(movecmd)
                    logger.info("Cleaning up SMS inbox.")

# These lines are for maintaining the net logs
        if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/netlog'):
           file = open('/home/pi/ioreth/ioreth/ioreth/netlog', 'r')
           data20 = file.read()
           file.close()
           fout = open(filename1, 'a')
           fout.write(data20)
           fout.write(",")
           fout = open(filename3, 'a')
           fout.write(data20)
           fout.write("\n")
           logger.info("Copying latest checkin into day's net logs")
           os.remove('/home/pi/ioreth/ioreth/ioreth/netlog')
           logger.info("Deleting net log scratch file")
           timestrtxt = time.strftime("%m%d")
           file = open(filename1, 'r')
           data5 = file.read()  
           file.close()
           if len(data5) > 310 :
                       listbody1 = data5[0:58]
                       listbody2 = data5[58:121]
                       listbody3 = data5[121:184]
                       listbody4 = data5[184:247]
                       listbody5 = data5[247:310]
                       listbody6 = data5[310:]
                       self._aprs.send_aprs_msg("BLN3NET", timestrtxt + " 1/6:" + listbody1)
                       self._aprs.send_aprs_msg("BLN4NET", "2/6:" + listbody2 )
                       self._aprs.send_aprs_msg("BLN5NET", "3/6:" + listbody3 )
                       self._aprs.send_aprs_msg("BLN6NET", "4/6:" + listbody4 )
                       self._aprs.send_aprs_msg("BLN7NET", "5/6:" + listbody5 )
                       self._aprs.send_aprs_msg("BLN8NET", "6/6:" + listbody6 )
           if len(data5) > 247 and len(data5) <= 310 :
                       listbody1 = data5[0:58]
                       listbody2 = data5[58:121]
                       listbody3 = data5[121:184]
                       listbody4 = data5[184:247]
                       listbody5 = data5[247:310]
                       self._aprs.send_aprs_msg("BLN4NET", timestrtxt + " 1/5:" + listbody1)
                       self._aprs.send_aprs_msg("BLN5NET", "2/5:" + listbody2 )
                       self._aprs.send_aprs_msg("BLN6NET", "3/5:" + listbody3 )
                       self._aprs.send_aprs_msg("BLN7NET", "4/5:" + listbody4 )
                       self._aprs.send_aprs_msg("BLN8NET", "5/5:" + listbody5 )
           if len(data5) > 184 and len(data5) <= 247 :
                       listbody1 = data5[0:58]
                       listbody2 = data5[58:121]
                       listbody3 = data5[121:184]
                       listbody4 = data5[184:]
                       self._aprs.send_aprs_msg("BLN5NET", timestrtxt + " 1/4:" + listbody1)
                       self._aprs.send_aprs_msg("BLN6NET", "2/4:" + listbody2 )
                       self._aprs.send_aprs_msg("BLN7NET", "3/4:" + listbody3 )
                       self._aprs.send_aprs_msg("BLN8NET", "4/4:" + listbody4 )
           if len(data5) > 121 and len(data5) <= 184:
                       listbody1 = data5[0:58]
                       listbody2 = data5[58:121]
                       listbody3 = data5[121:]
                       self._aprs.send_aprs_msg("BLN6NET", timestrtxt + " 1/3:" + listbody1)
                       self._aprs.send_aprs_msg("BLN7NET", "2/3:" + listbody2 )
                       self._aprs.send_aprs_msg("BLN8NET", "3/3:" + listbody3 )
           if len(data5) > 58 and len(data5) <= 121:
                       listbody1 = data5[0:58]
                       listbody2 = data5[58:]
                       self._aprs.send_aprs_msg("BLN6NET", timestrtxt + " 1/2:" + listbody1)
                       self._aprs.send_aprs_msg("BLN7NET", "2/2:" + listbody2 )
           if len(data5) <= 58:
                       self._aprs.send_aprs_msg("BLN6NET", timestrtxt + ":" + data5)
           self._aprs.send_aprs_msg("BLN9NET", "Full logs and more info at https://aprsph.net")
           logger.info("Sending new log text to BLN7NET to BLN8NET after copying over to daily log")

        if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/nettext'):
#           file = open('/home/pi/ioreth/ioreth/ioreth/nettext', 'r')
#           data4 = file.read()  
#           file.close()
# Deprecated the lines below. We are now writing the login text directly, since the previous method resulted in
# Simultaneous checkins not being logged properly. The purpose now is to use the nettext file as a flag whether to
# upload the net logs to the web.
#           fout = open('/home/pi/ioreth/ioreth/ioreth/netlog-msg', 'a')
#           fout.write(data4)
#           fout.write("\n")
#           fout.close()
#           logger.info("Copying latest checkin message into cumulative net log")
           os.remove('/home/pi/ioreth/ioreth/ioreth/nettext')
           logger.info("Deleting net text scratch file")
           cmd = 'scp -P 2202 /home/pi/ioreth/ioreth/ioreth/netlog-msg root@irisusers.com:/var/www/html/index.html'
#           cmd = 'scp /home/pi/ioreth/ioreth/ioreth/netlog-msg root@radio1.dx1arm.net:/var/www/aprsph.net/public_html/index.html'
#           cmd = 'scp /home/pi/ioreth/ioreth/ioreth/netlog-msg root@radio1.dx1arm.net:/var/www/html/aprsnet'
           try:
              os.system(cmd)
              logger.info("Uploading logfile to the web")
           except:
              logger.info("ERRIR in uploading logfile to the web")

        if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/aprsthursdaytext'):
           os.remove('/home/pi/ioreth/ioreth/ioreth/aprsthursdaytext')
           logger.info("Deleting aprsthursday net text scratch file")
           cmd = 'scp -P 2202 /home/pi/ioreth/ioreth/ioreth/aprsthursday/index.html root@irisusers.com:/var/www/html/aprsthursday/index.html'
#           cmd = 'scp /home/pi/ioreth/ioreth/ioreth/aprsthursday/index.html root@radio1.dx1arm.net:/var/www/aprsph.net/public_html/aprsthursday/index.html'
#           cmd = 'scp /home/pi/ioreth/ioreth/ioreth/netlog-msg root@radio1.dx1arm.net:/var/www/html/aprsnet'
           try:
              os.system(cmd)
              logger.info("Uploading aprsthursday logfile to the web")
           except:
              logger.info("ERRIR in uploading logfile to the web")








# No longer using the following lines.
#        if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/cqlog/cqmesg'):
#           file = open('/home/pi/ioreth/ioreth/ioreth/cqlog/cqmesg', 'r')
#           datacq = file.read()  
#           file.close()
#           cqout = open('/home/pi/ioreth/ioreth/ioreth/cqlog/cqlog', 'a')
#           cqout.write(datacq)
#           cqout.write("\n")
#           cqout.close()
#           logger.info("Copying latest net or checkin message into cumulative CQ message log")
#           os.remove('/home/pi/ioreth/ioreth/ioreth/cqlog/cqmesg')
#           logger.info("Deleting CQ text file")
#           cmd = 'scp /home/pi/ioreth/ioreth/ioreth/cqlog/cqlog root@radio1.dx1arm.net:/var/www/aprsph.net/public_html/cq/index.html'
#           os.system(cmd)
#           logger.info("Uploading cq to the web")

#        if os.path.isfile(icmesg):
#           file = open(icmesg, 'r')
#           datacq = file.read()  
#           file.close()
#           cqout = open(iclog, 'a')
#           cqout.write(datacq)
#           cqout.write("\n")
#           cqout.close()
#           logger.info("Copying latest IC message into cumulative IC message log")
#           os.remove(icmesg)
#           logger.info("Deleting IC text file")
#           cmd = 'scp /home/pi/ioreth/ioreth/ioreth/eric/eric root@radio1.dx1arm.net:/var/www/aprsph.net/public_html/ic/index.html'
#           os.system(cmd)
#           logger.info("Uploading cq to the web")


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

