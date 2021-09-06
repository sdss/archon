#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-04
# @Filename: test_command_reconnect.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from archon.actor import ArchonActor
from archon.exceptions import ArchonError


pytestmark = [pytest.mark.asyncio]


async def test_reconnect(actor: ArchonActor):

    command = await actor.invoke_mock_command("reconnect")
    await command

    assert command.status.did_succeed
    assert len(command.replies) == 2


async def test_reconnect_stop_fails(actor: ArchonActor, mocker):

    mocker.patch.object(
        actor.controllers["sp1"],
        "stop",
        side_effect=[ArchonError, None],  # stop() is also called on tear down.
    )

    command = await actor.invoke_mock_command("reconnect")
    await command

    assert command.status.did_fail  # Fails because the controller is still connected.
    assert len(command.replies) == 4


async def test_reconnect_not_running(actor: ArchonActor, mocker):

    await actor.controllers["sp1"].stop()

    command = await actor.invoke_mock_command("reconnect")
    await command

    assert command.status.did_succeed
    assert len(command.replies) == 2


async def test_reconnect_start_timesout(actor: ArchonActor, mocker):

    mocker.patch.object(
        actor.controllers["sp1"],
        "start",
        side_effect=asyncio.TimeoutError,
    )

    command = await actor.invoke_mock_command("reconnect")
    await command

    assert command.status.did_fail
    assert len(command.replies) == 3
