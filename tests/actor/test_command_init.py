#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-03
# @Filename: test_command_init.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest


pytestmark = [pytest.mark.asyncio]


async def test_init(actor):

    command = await actor.invoke_mock_command("init")
    await command

    assert command.status.did_succeed


async def test_init_controller_fails(actor):

    await actor.controllers["sp1"].stop()

    command = await actor.invoke_mock_command("init")
    await command

    assert command.status.did_fail


async def test_init_filename(actor, tmp_path):

    config_file = tmp_path / "test.acf"
    with open(config_file, "w") as f:
        f.write(
            """[CONFIG]
ADXCDS=0
ADXRAW=0
APPLYALL=0
BIGBUF=0
"""
        )

    command = await actor.invoke_mock_command(f"init {str(config_file)}")
    await command

    assert command.status.did_succeed


async def test_init_bad_filename(actor):

    command = await actor.invoke_mock_command("init dir/badfile.acf")
    await command

    assert command.status.did_fail
