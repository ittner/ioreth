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
# This fork of Ioreth was modified by Angelo 4I1RAC/N2RAC to support additional
# functionalities, such as a means to store callsigns from a "net" checkin
# as well as a means to forward messages to all stations checked in for the day
# It is also supported by local cron jobs on my own machine and web server
# to publish the net log on a regular basis.
# 
# Pardon my code. My knowledge is very rudimentary, and I only modify or create
# functions as I need them. If anyone can help improve on the code and the
# logic of this script, I would very much appreciate it.
# You may reach me at qsl@n2rac.com or simply APRS message me at N2RAC-7.
#
# A lot of the items here are still poorly documented if at all. Many also
# rely on some weird or nuanced scripts or directory structures that I have
# maintained on my own machine or server, so bear with me.
# The non-indented comments are mine. The indented ones are by Alexandre.
# A lot of this is trial-and-error for me, so again, please bear with me.
#
#

import sys
import time
import logging
import configparser
import os
import re
import random

logging.basicConfig()
logger = logging.getLogger(__name__)

from cronex import CronExpression
from .clients import AprsClient
from . import aprs
from . import remotecmd
from . import utils
from os import path


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


# Also Mmoved time string to place where it can be reset at midnight

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
        args = ""
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
            "73": "73 🖖",
        }

        if sourcetrunc == "DX1ARM-2":
                  logger.info("Message from self. Stop processing." )
                  return

        if qry == "ping":
            self.send_aprs_msg(sourcetrunc, "Pong! " + args )
        elif qry == "?aprst" or qry == "?ping?":
            tmp_lst = (
                origframe.to_aprs_string()
                .decode("utf-8", errors="replace")
                .split("::", 2)
            )
            self.send_aprs_msg(sourcetrunc, tmp_lst[0] + ":")
        elif qry == "version":
            self.send_aprs_msg(sourcetrunc, "Python " + sys.version.replace("\n", " "))
        elif qry == "about":
            self.send_aprs_msg(sourcetrunc, "APRS bot by N2RAC/4I1RAC based on ioreth by PP5ITT. aprs.dx1arm.net" )
        elif qry == "time":
            self.send_aprs_msg(
                sourcetrunc, "Localtime is " + time.strftime("%Y-%m-%d %H:%M:%S %Z")
            )
        elif qry == "help":
            self.send_aprs_msg(sourcetrunc, "NET +msg,CQ +msg,LIST,LAST,LOG,?APRST,SMS ### +msg,ABOUT,TIME,HELP")

# This part is the net checkin. It logs callsigns into a daily list, and it also logs all messages into a cumulative list posted on the web

        elif qry == "net" or qry == "checking" or qry == "checkin" or qry == "joining" or qry == "join" or qry == "hi" or qry =="hello" :
           sourcetrunc = source.replace('*','')
# Checking if duplicate message
# If not, write msg to temp file
           if not args == open('/home/pi/ioreth/ioreth/ioreth/lastmsg').read():
                  logger.info("Message is not exact duplicate, now logging" )

                  with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as g:
                       data3 = "{} {}: {}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
                       g.write(data3)
                       logger.info("Writing %s net message to netlog text", sourcetrunc)
# Checking if already in log
           with open(filename1, 'r') as file:
                 search_word = sourcetrunc
                 if(search_word in file.read()):
                      self.send_aprs_msg(sourcetrunc, "QSL ur addnl msg.CQ +msg,LIST,LOG,LAST,HELP.Net renews @1600Z daily")
                      logger.info("Checked if %s already logged to prevent duplicate. Skipping checkin", sourcetrunc)
                      file.close()
# If not in log, then add them
                 else:
                      with open('/home/pi/ioreth/ioreth/ioreth/netlog', 'w') as f:
                         f.write(sourcetrunc)
                         f.close()
                         logger.info("Writing %s checkin to netlog", source)
                      if args == "":
                         self.send_aprs_msg(sourcetrunc, "U may add txt aftr NET.CQ +text grp.LAST rvw last3.LIST view QRXlist.")
                      else:
                         self.send_aprs_msg(sourcetrunc, "QSL " + sourcetrunc + ". CQ +text grpchat.LAST review last3.LIST view QRXlist.")
                      self.send_aprs_msg(sourcetrunc, "Pls QRX for CQ msgs. Net renews @1600Z. aprs.dx1arm.net for info." )
                      logger.info("Replying to %s checkin message", sourcetrunc)

# Record the message somewhere to check if next message is dupe
           with open('/home/pi/ioreth/ioreth/ioreth/lastmsg', 'w') as g:
                lasttext = args
                g.write(lasttext)
                logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)
                g.close()

        elif qry == "list" or qry == "?aprsd":
           timestrtxt = time.strftime("%m%d")
           if os.path.isfile(filename1):
                 file = open(filename1, 'r')
                 data21 = file.read()
                 data2 = data21.replace('\n','')
                 file.close()
                 if len(data2) > 62:
                       listbody1 = data2[0:58]
                       listbody2 = data2[58:]
                       self.send_aprs_msg(source, timestrtxt + " 1/2:" + listbody1 )
                       self.send_aprs_msg(source, "2/2:" + listbody2 )
                       self.send_aprs_msg(source, "Send CQ +text to msg all in today's log. Info: aprs.dx1arm.net" )
                       logger.info("Replying with stations heard today. Exceeded length so split into 2: %s", data2 )
                 else:
                       self.send_aprs_msg(source, timestrtxt + ":" + data2 )
                       self.send_aprs_msg(source, "Send CQ +text to msg all in today's log. Info: aprs.dx1arm.net" )
                       logger.info("Replying with stations heard today: %s", data2 )
           else:
                 self.send_aprs_msg(source, "No stations have checked in yet. NET +msg to checkin.") 

        elif qry == "cq":
           sourcetrunc = source.replace('*','')
# Checking if duplicate message
           if not args == open('/home/pi/ioreth/ioreth/ioreth/lastmsg').read():
                  logger.info("Message is not exact duplicate, now logging" )

                  with open('/home/pi/ioreth/ioreth/ioreth/cqlog/cqmesg', 'w') as cqm:
                       data9 = "{} {}: {}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
                       cqm.write(data9)
                       logger.info("Writing %s CQ message to cqmesg", sourcetrunc)
                       cqm.close

# If no checkins, we will check you in and also post your CQ message into the CQ log, and also include in net log
           if not os.path.isfile(filename3):
               with open('/home/pi/ioreth/ioreth/ioreth/netlog', 'w') as nt:
                   nt.write(sourcetrunc)
                   logger.info("Writing %S message to netlog", sourcetrunc)
# Checking if duplicate message
               if not args == open('/home/pi/ioreth/ioreth/ioreth/lastmsg').read():
                   logger.info("Message is not exact duplicate, now logging" )
                   with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as ntg:
                        data3 = "{} {}: {}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
                        ntg.write(data3)
                        logger.info("Writing %s net message to netlog-msg", sourcetrunc)
               self.send_aprs_msg(sourcetrunc, "No stations QRX  yet. Ur nw checked in today's log." ) 
               logger.info("Advising %s to checkin", sourcetrunc)
               return
# If not yet in log, add them in and add their message to net log.
           file = open(filename1, 'r')
           search_word = sourcetrunc
           if not (search_word in file.read()):
                with open('/home/pi/ioreth/ioreth/ioreth/netlog', 'w') as cqf:
                      cqf.write(sourcetrunc)
                      logger.info("CQ source not yet in net. Writing %s checkin to netlog", source)
                with open('/home/pi/ioreth/ioreth/ioreth/nettext', 'w') as ntg:
                      data3 = "{} {}: {}".format(time.strftime("%Y-%m-%d %H:%M:%S %Z"), sourcetrunc, args)
                      ntg.write(data3)
                      logger.info("Writing %s net message to netlog-msg", sourcetrunc)
# Record the message somewhere to check if next message is dupe
           with open('/home/pi/ioreth/ioreth/ioreth/lastmsg', 'w') as g:
                lasttext = args
                g.write(lasttext)
                logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)

# Send the message to all on the QRX list for today
           lines = []
           with open(filename3) as sendlist:
                lines = sendlist.readlines()
           count = 0
           for line in lines:
                linetrunc = line.replace('\n','')
                count += 1
                if not sourcetrunc == linetrunc:
                      self.send_aprs_msg(linetrunc, sourcetrunc + ">" + args)
                      self.send_aprs_msg(linetrunc, "Reply CQ +text to send all on today's list. LIST to view." )
                logger.info("Sending CQ message to %s except %s", linetrunc, sourcetrunc)
# This reads the day's log from a line-separated list for processing one message at a time.
# Advise sender their message is sent
           daylog = open(filename1, 'r')
           dayta2 = daylog.read() 
           daylog.close()
           dayta31 = dayta2.replace(sourcetrunc + ',','')
           dayta3 = dayta31.replace('\n','')
           self.send_aprs_msg(source, "QSP " + dayta3 )
           logger.info("Advising %s of messages sent to %s", sourcetrunc, dayta3)


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
                  logger.info("Sending DU message to %s", line)
             file = open(dusubslist, 'r')
             data21 = file.read()  
             data2 = data21.replace('\n','')
             file.close()
             self.send_aprs_msg(source, "Sent msg to QST recipients. Ask DU2XXR for list." )
             logger.info("Advising %s of messages sent to %s", sourcetrunc, data2)
#             file.close()
        elif qry == "last": 
             with open(cqlog) as netlast:
                  lasts = netlast.readlines()
                  lastlines = lasts[-3:]
                  netlast.close()
             self.send_aprs_msg(sourcetrunc, "Last 3 CQ msgs sent. CQ +text to reply,LIST for QRX,HELP for cmds." )
             count = 0
             for line in lastlines:
                  count +=1
                  self.send_aprs_msg(sourcetrunc, str(count) + "." + line[24:91] )
                  logger.info("Sending last 3 cqlog messages to  %s", sourcetrunc)
        elif qry == "log":
             with open(filename2) as netlast:
                  lasts = netlast.readlines()
                  lastlines = lasts[-3:]
                  netlast.close()
             self.send_aprs_msg(sourcetrunc, "Last 3 NET msgs. NET +text to join,LIST for QRX,HELP for cmds." )
             count = 0
             for line in lastlines:
                  count +=1
                  self.send_aprs_msg(sourcetrunc, str(count) + "." + line[24:91] )
                  logger.info("Sending last 3 netlog messages to  %s", sourcetrunc)



# Let users set up SMS aliases. Be sure to create the paths yourself if not yet existent.
        elif qry == "smsalias" or qry == "setalias":
             sourcetrunc = source.replace('*','')
             callnossid = sourcetrunc.split('-', 1)[0]
             SMS_DESTINATION = args[0:11]
             SMS_ALIAS = args[12:]
             aliasscratch = "/home/pi/ioreth/ioreth/ioreth/smsaliasscratch/" + callnossid
             aliasfile = "/home/pi/ioreth/ioreth/ioreth/smsalias/" + callnossid
# stop processing duplicates, since APRS sends messages multiple times.
             if not os.path.isfile(aliasscratch):
                 aliases = open(aliasscratch, 'w')
             if args == open(aliasscratch).read():
                 logger.info("Already processed alias for %s %s recently. No longer processing.", SMS_DESTINATION, SMS_ALIAS)
                 return
             if not args[0:2] == "09":
                 self.send_aprs_msg(sourcetrunc, "SMSALIAS 09XXXXXXXXX name to set. SMS NAME to send thereafter.")
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
          sourcetrunc = source.replace('*','')
          callnossid = sourcetrunc.split('-', 1)[0]
          SMS_TEXT = ("APRS msg fr " + sourcetrunc + " via DX1ARM-2:\n\n" + args.split(' ', 1)[1] + "\n\n@" + sourcetrunc + " plus ur msg to reply. APRS MSGs ARE NOT PRIVATE!" )
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

          if not args == open('/home/pi/ioreth/ioreth/ioreth/lastmsg').read():
             logger.info("Received message for SMS that is not exact duplicate, now sending SMS" )

             if args == "":
                 self.send_aprs_msg(sourcetrunc, "SMS 09XXXXXXXXX msg. PH#s only. SMSALIAS # name to set nicknames." )
                 logger.info("Replying to %s about SMS instructions", sourcetrunc)
                 return


             with open('/home/pi/ioreth/ioreth/ioreth/lastmsg', 'w') as g:
                   lasttext = args
                   g.write(lasttext)
                   logger.info("Writing %s message somewhere to check for future dupes", sourcetrunc)
             sourcetrunc = source.replace('*','')

# Validating the destination. In the Philippines, cell numbers start with 09XX. Adjust this accordingly.

             if not SMS_DESTINATION[0:2] == "09":
                 self.send_aprs_msg(sourcetrunc, "Num or SMSALIAS invalid. Usage:SMS 09XXXXXXXXX or alias msg. PH# only" )
                 logger.info("Replying to %s that %s is not a valid number.", sourcetrunc, SMS_DESTINATION)
                 return

             try:
#                   os.system(sendsms)
                   self.send_aprs_msg(sourcetrunc, "SMS " + smsoralias +" -sending. Note: APRS msgs not private." )
                   aliasfile = "/home/pi/ioreth/ioreth/ioreth/smsalias/" + callnossid
                   smsoralias = args.split(' ', 1)[0]
                   if not os.path.isfile(aliasfile):
                         self.send_aprs_msg(sourcetrunc, "U may use alias.SMSALIAS 09XXXXXXXXX NAME to set.SMS NAME to send.")
                   logger.info("Replying to %s that SMS to %s is being sent", sourcetrunc, SMS_DESTINATION)
                   os.system(sendsms)
                   logger.info("Sending SMS from %s to %s", sourcetrunc, SMS_DESTINATION)
             except:
                   self.send_aprs_msg(sourcetrunc, 'SMS Could not be sent')
                   logger.info("Could not send SMS from %s to %s", sourcetrunc, SMS_DESTINATION)

# This is necessary, since APRS messages may be sent or received multiple times (e.g., heard from another digipeater)
# This ensures that the SMS being sent will not be doubled. When the same message is heared on this machine, processing
# Stops already because the message has been queued by Gammu-smsd. Same case with other processes here.

          else:
             logger.info("SMS fromm %s to %s is a duplicate. No longer processing", sourcetrunc, SMS_DESTINATION)

        elif qry in random_replies:
            self.send_aprs_msg(sourcetrunc, random_replies[qry] )

# These lines are for executing certain commands on the server, such as rebooting, etc.
# Make sure the account has sufficient privileges!

# This reboots the system
        elif qry == "YOURCOMMAND" and source == "YOURCALLSIGN":
             self.send_aprs_msg(sourcetrunc, "bye" )
             cmd = 'sudo shutdown --reboot'
             os.system(cmd)

# This reboots another connected system within the local network. There is option
# For different source callsigns to issue the command.
# Not very secure, but hey what's the worst that they can do? Just reboot it!
# Besides, you have the option of using some obscure word that you will only use
# occassionaly or only once whnen something goes wrong. This is great for APRS digis/machines
# that are in unattended locations such as repeater sites.
# You can even execute server-side scripts depending on your need.

        elif qry == "YOURCOMMAND2" and ( source == "CALLSIGN1" or "CALLSIGN2" or  "CALLSIGN3" ):
             os.system('ssh user@otherserver sudo shutdown --reboot')
             self.send_aprs_msg(sourcetrunc, "ttfn" )

        else:
            self.send_aprs_msg(sourcetrunc, "NET +text to checkin,CQ +text grp msg,LIST to view,HELP for cmds." )
            with open('/home/pi/ioreth/ioreth/ioreth/lastmsg', 'w') as g:
                lasttext = args
                g.write(lasttext)
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
        smsproc = "ls -l /var/spool/gammu/processed | grep total > /home/pi/ioreth/ioreth/ioreth/smsrxcount"
        smsrxcount = os.system(smsproc)
        smssent = "ls -l /var/spool/gammu/sent | grep total > /home/pi/ioreth/ioreth/ioreth/smstxcount"
        smstxcount = os.system(smssent)
        

        smsrxnum = open('/home/pi/ioreth/ioreth/ioreth/smsrxcount', 'r')
        smsrxcounts = smsrxnum.read()
        smsrxtotals1 = smsrxcounts.replace('total ','')
        smsrxtotals = smsrxtotals1.replace('\n','')
        smsrxnum.close()

        smstxnum = open('/home/pi/ioreth/ioreth/ioreth/smstxcount', 'r')
        smstxcounts = smstxnum.read()
        smstxtotals1 = smstxcounts.replace('total ','')
        smstxtotals = smstxtotals1.replace('\n','')
        smstxnum.close()

        net_status = (
            self._check_host_scope("Link", "eth_host")
            + self._check_host_scope("YSF", "inet_host")
            + self._check_host_scope("VHF", "dns_host")
            + self._check_host_scope("VPN", "vpn_host")
        )
        self.status_str = "NET to checkin.HELP 4 cmds.SMS R%s T%s Up:%s" % (
#            time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            smsrxtotals,
            smstxtotals,
            utils.human_time_interval(utils.get_uptime()),
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
                          cellownalias = smsreceived.split(' ', 1)[1]
                          aliastext = smssender + " " + cellownalias
                          with open(cellaliasfile, 'a') as makealias:
                              writealias = "{} {}\n".format(smssender, cellownalias)
                              makealias.write(writealias)
                          sendsms = ( "echo 'U have set ur own alias as " + cellownalias + ". Ur # will not appear on APRS msgs. Go aprs.dx1arm.net for more info.' | gammu-smsd-inject TEXT 0" + smsnumber )
                          os.system(sendsms)
                          logger.info("Self-determined alias set for for %s as %s.", smsnumber, cellownalias )
                      elif smsreceived[0:1] == "@":
                          callsig = smsreceived.split(' ', 1)[0]
                          callsign = callsig.upper()
                          callnossid = callsign.split('-', 1)[0]
                          smsbody = smsreceived.split(' ', 1)[1]
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
                               self._aprs.send_aprs_msg(callsign[1:], "SMS " + smssender+ " Message to send/reply to PH SMS.")
                               logger.info("SMS is in correct format. Sending to %s.", callsign)
                          if smsalias == 1 or cellsmsalias == 1:
                               sendsms = ( "echo 'APRS msg to " + callsign[1:] + " has been sent. APRS msgs not private, but ur # has an alias & will not appear. Go aprs.dx1arm.net for more info.' | gammu-smsd-inject TEXT 0" + smsnumber )
                          else:
                               sendsms = ( "echo 'APRS msg to " + callsign[1:] + " sent. Ur # & msg may appear on online services. Send ALIAS yourname to set an alias. Go aprs.dx1arm.net for more info.' | gammu-smsd-inject TEXT 0" + smsnumber )
                          logger.info("Sending %s a confirmation message that APRS message has been sent.", smssender)
                          os.system(sendsms)
                      else:
#                          if smsalias == 1:
                          sendsms = ( "echo 'To text APRS user: \n\n@CALSGN-SSID Message\n\nMust hv @ b4 CS (SSID optional if none). To set ur alias & mask ur cell#:\n\nALIAS myname\n\naprs.dx1arm.net for info.' | gammu-smsd-inject TEXT 0" + smsnumber )
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
           if len(data5) > 58:
                       listbody1 = data5[0:58]
                       listbody2 = data5[58:]
                       self._aprs.send_aprs_msg("BLN7NET", timestrtxt + " 1/2:" + listbody1)
                       self._aprs.send_aprs_msg("BLN8NET", "2/2:" + listbody2 )
           else:
                       self._aprs.send_aprs_msg("BLN7NET", timestrtxt + ":" + data5)
           self._aprs.send_aprs_msg("BLN9NET", "Full logs at http://aprs.dx1arm.net & http://cq.dx1arm.net")
           logger.info("Sending new log text to BLN7NET to BLN8NET after copying over to daily log")

        if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/nettext'):
           file = open('/home/pi/ioreth/ioreth/ioreth/nettext', 'r')
           data4 = file.read()  
           file.close()
           fout = open('/home/pi/ioreth/ioreth/ioreth/netlog-msg', 'a')
           fout.write(data4)
           fout.write("\n")
           fout.close()
           logger.info("Copying latest checkin message into cumulative net log")
           os.remove('/home/pi/ioreth/ioreth/ioreth/nettext')
           logger.info("Deleting net text scratch file")
           cmd = 'scp /home/pi/ioreth/ioreth/ioreth/netlog-msg root@radio1.dx1arm.net:/var/www/html/aprsnet'
           os.system(cmd)
           logger.info("Uploading logfile to the web")

        if os.path.isfile('/home/pi/ioreth/ioreth/ioreth/cqlog/cqmesg'):
           file = open('/home/pi/ioreth/ioreth/ioreth/cqlog/cqmesg', 'r')
           datacq = file.read()  
           file.close()
           cqout = open('/home/pi/ioreth/ioreth/ioreth/cqlog/cqlog', 'a')
           cqout.write(datacq)
           cqout.write("\n")
           cqout.close()
           logger.info("Copying latest net or checkin message into cumulative CQ message log")
           os.remove('/home/pi/ioreth/ioreth/ioreth/cqlog/cqmesg')
           logger.info("Deleting CQ text file")
           cmd = 'scp /home/pi/ioreth/ioreth/ioreth/cqlog/cqlog root@radio1.dx1arm.net:/var/www/html/cqlog'
           os.system(cmd)
           logger.info("Uploading cq to the web")


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

