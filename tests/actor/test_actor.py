#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-03
# @Filename: test_actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest

from archon.actor import ArchonActor


async def test_actor(actor: ArchonActor):

    assert actor
    assert len(actor.controllers) == 1
    assert actor.controllers["sp1"].is_connected()


async def test_ping(actor):

    command = await actor.invoke_mock_command("ping")
    await command

    assert command.status.did_succeed
    assert len(command.replies) == 2
    assert command.replies[1].message["text"] == "Pong."


async def test_actor_no_config():

    with pytest.raises(RuntimeError):
        ArchonActor.from_config(None)
