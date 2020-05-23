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
import multiprocessing as mp
import queue


logging.basicConfig()
logger = logging.getLogger(__name__)


class BaseRemoteCommand:
    """A 'remote command' to be ran in the helper process.
    """

    def __init__(self, token):
        self.token = token

    def run(self):
        """Run the command. Should be redefined by the actual command.
        """
        pass


class RemoteCommandHandler:
    """Run "commands" in an external process using the multiprocessing
    module. When finished they are returned to the calling process in a
    return queue.

    Overhead here is enormous. The idea is only use this for things that
    demand information from external sources or thar should be isolated
    from the main process.
    """

    def __init__(self):
        self._ctx = mp.get_context("spawn")
        self._in_queue = self._ctx.Queue()
        self._out_queue = self._ctx.Queue()
        self._proc = None

    def _start_proc(self):
        if not self._proc:
            self._proc = self._ctx.Process(
                target=RemoteCommandHandler._remote_loop,
                args=(self._in_queue, self._out_queue),
            )
            self._proc.start()

    def _stop_proc(self):
        if self._proc:
            self.post_cmd("quit")
            self._proc.join()
            self._proc = None

    def post_cmd(self, cmd):
        """Post a new command to be ran in the helper process.
        """
        if not self._proc:
            self._start_proc()
        self._in_queue.put(cmd)

    def poll_ret(self):
        """Check if there finished command in the remote process.
        Return: ran command or None
        """
        ret = None
        try:
            ret = self._out_queue.get(False)
        except queue.Empty:
            pass
        return ret

    @staticmethod
    def _remote_loop(in_queue, out_queue):
        """Executes commands in an external processes
        """
        while True:
            cmd = in_queue.get(True)
            if cmd == "quit":
                break
            elif isinstance(cmd, BaseRemoteCommand):
                cmd.run()
                out_queue.put(cmd)
