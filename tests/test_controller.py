#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-20
# @Filename: test_controller.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from archon.controller.command import ArchonCommand
from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError, ArchonUserWarning

pytestmark = [pytest.mark.asyncio]


@pytest.mark.commands([["PING", ["<{cid}PONG"]]])
async def test_controller(controller: ArchonController):
    assert controller.host == "localhost"
    command = controller.send_command("ping")
    await command
    assert command.status == command.status.DONE
    assert command.replies[0].reply == "PONG"
    assert str(command.replies[0]) == "PONG"


@pytest.mark.commands([["PING", [b"<{cid}:12345"]]])
async def test_controller_binary_reply(controller: ArchonController):
    command = controller.send_command("ping")
    await command
    assert command.status == command.status.DONE
    assert len(command.replies) == 1
    assert len(command.replies[0].reply) == 1024
    assert command.replies[0].reply.strip() == b"12345"
    with pytest.raises(ArchonError):
        str(command.replies[0])


@pytest.mark.commands([["PING", ["?{cid}"]]])
async def test_controller_error(controller: ArchonController):
    command = controller.send_command("ping")
    await command
    assert command.status == command.status.FAILED
    assert command.replies[0].type == "?"


@pytest.mark.commands([["PING", ["<?!PONG"]]])
async def test_controller_command_not_running(controller: ArchonController):
    with pytest.warns(ArchonUserWarning):
        controller.send_command("ping")
        await asyncio.sleep(0.01)


@pytest.mark.commands([["PING", ["<02PONG"]]])
async def test_controller_bad_reply(controller: ArchonController):
    with pytest.warns(ArchonUserWarning):
        controller.send_command("ping", command_id=1)
        await asyncio.sleep(0.01)


@pytest.mark.commands([])
async def test_controller_wrap_command_id(controller: ArchonController):
    controller._ArchonController__next_id = 2 ** 8 - 1  # type: ignore (mangled)
    command = controller.send_command("PING")
    assert command.command_id == 2 ** 8 - 1
    command = controller.send_command("PING")
    assert command.command_id == 0


@pytest.mark.commands([])
@pytest.mark.parametrize("command_id", [-1, 256])
async def test_controller_bad_command_id(
    controller: ArchonController,
    command_id: int,
):
    with pytest.raises(ArchonError):
        controller.send_command("PING", command_id=command_id)


@pytest.mark.parametrize("command_id", [-5, 2 ** 8 + 1])
def test_command_bad_command_id(command_id):
    with pytest.raises(ValueError):
        ArchonCommand("ping", command_id)


@pytest.mark.parametrize("reply", [b"bad_reply", b"<02PONG"])
def test_command_process_bad_reply(reply):
    command = ArchonCommand("ping", 1)

    with pytest.warns(ArchonUserWarning):
        command.process_reply(reply)

    assert command.status == command.status.FAILED


def test_command_process_reply_failed():
    command = ArchonCommand("ping", 1)
    command.process_reply(b"?01")
    assert command.status == command.status.FAILED


async def test_command_two_replies():
    command = ArchonCommand("ping", 1, expected_replies=2, timeout=0.1)
    assert command.status == command.status.RUNNING
    command.process_reply(b"<01pong1")
    assert command.status == command.status.RUNNING
    await asyncio.sleep(0.01)
    command.process_reply(b"<01pong2")
    assert command.status == command.status.DONE


async def test_command_timeout():
    command = ArchonCommand("ping", 1, expected_replies=2, timeout=0.01)
    assert command.status == command.status.RUNNING
    await asyncio.sleep(0.02)
    assert command.status == command.status.TIMEDOUT


async def test_command_get_replies():
    async def background(command: ArchonCommand):
        command.process_reply(b"<01pong1")
        await asyncio.sleep(0.01)
        command.process_reply(b"<01pong1")
        await asyncio.sleep(0.02)
        command._mark_done()

    command = ArchonCommand("ping", 1, expected_replies=None)
    asyncio.create_task(background(command))

    replies = []
    async for reply in command.get_replies():
        replies.append(reply)

    assert command.status == command.status.DONE
    assert len(replies) == 2
