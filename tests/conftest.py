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

from typing import Iterable, Tuple

import pytest

from archon.controller.controller import ArchonController


@pytest.fixture()
async def controller(request, unused_tcp_port: int):
    """Mocks a `.ArchonController` that replies to commands with predefined replies.

    Tests that use this fixture must be decorated with ``@pytest.mark.commands``. The
    arguments are a list of input commands and replies. For example
    ``@pytest.mark.commands.commands=[['STATUS', ['VALID=1 COUNT=379780 LOG=4']]]``
    will reply with ``<xxVALID=1 COUNT=379780 LOG=4`` to the commands ``>xxSTATUS``.
    Do not include the command id in the definition. If the reply is an instance of
    bytes, it will be returned as a binary response.
    """
    commands: Iterable[
        Tuple[str, Iterable[str | bytes]]
    ] = request.node.get_closest_marker("commands").args[0]

    async def handle_connection(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            data = await reader.readuntil()
            data = data.decode()

            matched = re.match("^>([0-9A-F]{2})(.+)\n$", data)
            if not matched:
                continue

            cid, com = matched.groups()

            replied = False
            for (command, replies) in commands:
                if command.upper() == com.upper():
                    if isinstance(replies, str):
                        replies = [replies]
                    for reply in replies:
                        if isinstance(reply, str):
                            reply = reply.encode()
                            binary_sep = b""
                            endline = b"\n"
                        else:
                            reply = reply.ljust(1024, b" ")
                            binary_sep = b":"
                            endline = b"\n"
                        writer.write(b"<" + cid.encode() + binary_sep + reply + endline)
                        await writer.drain()
                        replied = True
                    break
            if replied:
                continue
            writer.write(b"?{cid}\n")

    server = await asyncio.start_server(handle_connection, "localhost", unused_tcp_port)

    async with server:
        archon = ArchonController("localhost", unused_tcp_port)
        await archon.start()

        yield archon

        await archon.stop()