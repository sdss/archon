#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-06
# @Filename: test_command_expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os

from typing import Any

import pytest
from astropy.io import fits

from archon.actor.actor import ArchonActor
from archon.exceptions import ArchonError


pytestmark = [pytest.mark.asyncio]


async def test_expose_start(delegate, actor: ArchonActor):

    command = await actor.invoke_mock_command("expose start 0.01")
    await command

    assert command.status.did_succeed


async def test_expose_start_controller_list(delegate, actor: ArchonActor):

    command = await actor.invoke_mock_command("expose start --controller sp1 0.01")
    await command

    assert command.status.did_succeed


async def test_expose_start_controller_list_bad_name(delegate, actor: ArchonActor):

    command = await actor.invoke_mock_command("expose start --controller sp5 0.01")
    await command

    assert command.status.did_fail


async def test_expose_start_bad_controller(delegate, actor: ArchonActor):

    await actor.controllers["sp1"].stop()

    command = await actor.invoke_mock_command("expose start --controller sp1 0.01")
    await command

    assert command.status.did_fail


async def test_expose_start_no_delegate(delegate, actor: ArchonActor):

    actor.expose_delegate = None  # type: ignore

    command = await actor.invoke_mock_command("expose start --controller sp1 0.01")
    await command

    assert command.status.did_fail


async def test_expose_start_expose_fails(delegate, actor: ArchonActor, mocker):
    async def fail(command, *args, **kwargs):
        command.fail()
        return False

    mocker.patch.object(actor.expose_delegate, "expose", side_effect=fail)

    command = await actor.invoke_mock_command("expose start sp1 0.01")
    await command

    assert command.status.did_fail


async def test_expose_finish(delegate, actor: ArchonActor):

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    finish = await actor.invoke_mock_command("expose finish")
    await finish

    assert finish.status.did_succeed


async def test_expose_finish_header(delegate, actor: ArchonActor):

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    finish = await actor.invoke_mock_command(
        'expose finish --header \'{"key1": 666, "key2": ["hi", "Greetings"]}\''
    )
    await finish

    assert finish.status.did_succeed

    filename = delegate.actor.model["filename"].value
    assert os.path.exists(filename)

    hdu: Any = fits.open(filename)
    assert hdu[0].data.shape == (2048, 2048)
    assert hdu[0].header["CCDTEMP1"] == -110
    assert hdu[0].header["KEY1"] == 666
    assert hdu[0].header["KEY2"] == "hi"


async def test_expose_finish_no_delegate(delegate, actor: ArchonActor):

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    actor.expose_delegate = None  # type: ignore

    command = await actor.invoke_mock_command("expose finish")
    await command

    assert command.status.did_fail


async def test_expose_finish_expose_fails(delegate, actor: ArchonActor, mocker):
    async def fail(command, *args, **kwargs):
        command.fail()
        return False

    mocker.patch.object(actor.expose_delegate, "readout", side_effect=fail)

    command = await actor.invoke_mock_command("expose finish")
    await command

    assert command.status.did_fail


async def test_expose_abort(delegate, actor: ArchonActor):

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    abort = await actor.invoke_mock_command("expose abort")
    await abort

    assert abort.status.did_succeed


async def test_expose_abort_no_expose_data(delegate, actor: ArchonActor):

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    actor.expose_delegate.expose_data = None

    abort = await actor.invoke_mock_command("expose abort")
    await abort

    assert abort.status.did_fail


async def test_expose_abort_no_expose_data_force(delegate, actor: ArchonActor):

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    actor.expose_delegate.expose_data = None

    abort = await actor.invoke_mock_command("expose abort --force")
    await abort

    assert abort.status.did_succeed


async def test_expose_abort_no_expose_data_all(delegate, actor: ArchonActor):

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    actor.expose_delegate.expose_data = None

    abort = await actor.invoke_mock_command("expose abort --all")
    await abort

    assert abort.status.did_succeed


async def test_expose_abort_fails(delegate, actor: ArchonActor, mocker):

    mocker.patch.object(actor.controllers["sp1"], "abort", side_effect=ArchonError)

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    abort = await actor.invoke_mock_command("expose abort")
    await abort

    assert abort.status.did_fail


async def test_expose_abort_flush(delegate, actor: ArchonActor, mocker):

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    abort = await actor.invoke_mock_command("expose abort --flush")
    await abort

    assert abort.status.did_succeed


async def test_expose_abort_flush_fails(delegate, actor: ArchonActor, mocker):

    mocker.patch.object(actor.controllers["sp1"], "flush", side_effect=ArchonError)

    start = await actor.invoke_mock_command("expose start 0.01")
    await start

    abort = await actor.invoke_mock_command("expose abort --flush")
    await abort

    assert abort.status.did_fail
