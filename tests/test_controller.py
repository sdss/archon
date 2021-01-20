#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-20
# @Filename: test_controller.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from archon.controller.controller import ArchonController

pytestmark = [pytest.mark.asyncio]


@pytest.mark.commands([["PING", ["PONG"]]])
async def test_connection(controller: ArchonController):
    assert controller.host == "localhost"
    command = controller.send_command("ping")
    await asyncio.sleep(0.01)
    assert command.status == command.status.DONE
    assert command.replies == ["PONG"]


@pytest.mark.commands([["PING", [b"12345"]]])
async def test_binary_reply(controller: ArchonController):
    assert controller.host == "localhost"
    command = controller.send_command("ping")
    await asyncio.sleep(0.01)
    assert command.status == command.status.DONE
    assert len(command.replies) == 1
    assert len(command.replies[0]) == 1024
    assert command.replies[0].strip() == b"12345"
