#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-20
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import re

from typing import Iterable, Tuple, Union

import pytest

from archon import config
from archon.controller.controller import ArchonController
from archon.controller.maskbits import ControllerStatus


config["archon"]["default_parameters"]["Exposures"] = 0


CommandsType = Iterable[Tuple[str, Iterable[Union[str, bytes]]]]


@pytest.fixture()
async def controller(request, unused_tcp_port: int):
    """Mocks a `.ArchonController` that replies to commands with predefined replies.

    Tests that use this fixture must be decorated with ``@pytest.mark.commands``. The
    arguments are a list of input commands and replies. For example
    ``@pytest.mark.commands.commands=[['STATUS', ['<{cid}VALID=1 COUNT=379780']]]``
    will reply with ``<01VALID=1 COUNT=379780\n`` to the commands ``>01STATUS``.
    The command of the reply can be hardcoded or use ``{cid}`` for a placeholder that
    will be replaced with the actual command id. If the reply is an instance of
    bytes, it will be returned as a binary response.
    """

    try:
        commands: CommandsType = request.node.get_closest_marker("commands").args[0]
    except AttributeError:
        commands: CommandsType = []

    async def handle_connection(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            data = await reader.readuntil()
            data = data.decode()

            matched = re.match(
                r"^>([0-9A-F]{2})(FRAME|SYSTEM|FASTLOADPARAM|PING|STATUS|FETCH|LOCK|"
                r"CLEARCONFIG|RCONFIG|RESETTIMING|HOLDTIMING|RELEASETIMING|"
                r"APPLYALL|POWERON|WCONFIG|POLLON|POLLOFF).*\n$",
                data,
            )
            if not matched:
                continue

            cid, com = matched.groups()

            found_command = False
            for (command, replies) in commands:
                if command.upper() == com.upper():
                    if isinstance(replies, str):
                        replies = [replies]
                    for reply in replies:
                        if isinstance(reply, str):
                            reply = (reply.format(cid=cid) + "\n").encode()
                        else:
                            reply = reply.replace(b"{cid}", cid.encode()).ljust(
                                1028, b" "
                            )
                        writer.write(reply)
                        await writer.drain()
                        found_command = True
                    break

            # Default reply
            if not found_command:
                if com.upper() == "STATUS":
                    writer.write(f"<{cid}POWERGOOD=1\n".encode())
                else:
                    writer.write(f"<{cid}\n".encode())
                await writer.drain()

    server = await asyncio.start_server(handle_connection, "localhost", unused_tcp_port)

    async with server:
        archon = ArchonController("localhost", unused_tcp_port, name="test_controller")
        await archon.start(reset=False)
        archon._status = ControllerStatus.IDLE

        yield archon

        await archon.stop()
