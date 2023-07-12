#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-06
# @Filename: test_command_expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import os
import sys

from typing import Any

import pytest
from astropy.io import fits

from archon.actor.actor import ArchonActor
from archon.exceptions import ArchonError


async def test_expose_start(delegate, actor: ArchonActor):
    command = await actor.invoke_mock_command("expose --no-readout 0.01")
    await command

    assert command.status.did_succeed


async def test_expose_start_controller_list(delegate, actor: ArchonActor):
    command = await actor.invoke_mock_command(
        "expose --no-readout --controller sp1 0.01"
    )
    await command

    assert command.status.did_succeed


async def test_expose_start_controller_list_bad_name(delegate, actor: ArchonActor):
    command = await actor.invoke_mock_command(
        "expose --no-readout --controller sp5 0.01"
    )
    await command

    assert command.status.did_fail


async def test_expose_start_bad_controller(delegate, actor: ArchonActor):
    await actor.controllers["sp1"].stop()

    command = await actor.invoke_mock_command(
        "expose --no-readout --controller sp1 0.01"
    )
    await command

    assert command.status.did_fail


async def test_expose_start_no_delegate(delegate, actor: ArchonActor):
    actor.expose_delegate = None  # type: ignore

    command = await actor.invoke_mock_command(
        "expose --no-readout --controller sp1 0.01"
    )
    await command

    assert command.status.did_fail


async def test_expose_start_expose_fails(delegate, actor: ArchonActor, mocker):
    async def fail(command, *args, **kwargs):
        command.fail()
        return False

    mocker.patch.object(actor.expose_delegate, "expose", side_effect=fail)

    command = await actor.invoke_mock_command("expose --no-readout sp1 0.01")
    await command

    assert command.status.did_fail


async def test_expose_read(delegate, actor: ArchonActor):
    await (await actor.invoke_mock_command("expose --no-readout 0.01"))

    read = await actor.invoke_mock_command("read")
    await read

    assert read.status.did_succeed


async def test_expose_read_header(delegate, actor: ArchonActor):
    await (await actor.invoke_mock_command("expose --no-readout 0.01"))

    read = await actor.invoke_mock_command(
        'read --header \'{"key1": 666, "key2": ["hi", "Greetings"]}\''
    )
    await read

    assert read.status.did_succeed

    filename = delegate.actor.model["filenames"].value[0]
    assert os.path.exists(filename)

    hdu: Any = fits.open(filename)
    assert hdu[0].data.shape == (800, 800)
    assert hdu[0].header["CCDTEMP1"] == -110
    assert hdu[0].header["KEY1"] == 666
    assert hdu[0].header["KEY2"] == "hi"


async def test_expose_read_no_delegate(delegate, actor: ArchonActor):
    await actor.invoke_mock_command("expose --no-readout 1")
    await asyncio.sleep(0.05)

    actor.expose_delegate = None  # type: ignore

    command = await actor.invoke_mock_command("read")
    await command

    assert command.status.did_fail


async def test_expose_read_expose_fails(delegate, actor: ArchonActor, mocker):
    async def fail(command, *args, **kwargs):
        command.fail()
        return False

    mocker.patch.object(actor.expose_delegate, "readout", side_effect=fail)

    command = await actor.invoke_mock_command("read")
    await command

    assert command.status.did_fail


async def test_expose_abort(delegate, actor: ArchonActor):
    await actor.invoke_mock_command("expose --no-readout 1")
    await asyncio.sleep(0.05)

    abort = await actor.invoke_mock_command("abort")
    await abort

    assert abort.status.did_succeed


async def test_expose_abort_no_expose_data(delegate, actor: ArchonActor):
    await actor.invoke_mock_command("expose --no-readout 1")
    await asyncio.sleep(0.05)

    actor.expose_delegate.expose_data = None

    abort = await actor.invoke_mock_command("abort")
    await abort

    assert abort.status.did_fail


@pytest.mark.skipif(sys.version_info < (3, 9), reason="seems to fail in PY38")
async def test_expose_abort_no_expose_data_force(delegate, actor: ArchonActor):
    await actor.invoke_mock_command("expose --no-readout 1")
    await asyncio.sleep(0.05)

    actor.expose_delegate.expose_data = None

    abort = await actor.invoke_mock_command("abort --force")
    await abort

    assert abort.status.did_succeed


@pytest.mark.skipif(sys.version_info < (3, 9), reason="seems to fail in PY38")
async def test_expose_abort_no_expose_data_all(delegate, actor: ArchonActor):
    await actor.invoke_mock_command("expose --no-readout 1")
    await asyncio.sleep(0.05)

    actor.expose_delegate.expose_data = None

    abort = await actor.invoke_mock_command("abort --all")
    await abort

    assert abort.status.did_succeed


async def test_expose_abort_fails(delegate, actor: ArchonActor, mocker):
    mocker.patch.object(actor.controllers["sp1"], "abort", side_effect=ArchonError)

    await actor.invoke_mock_command("expose --no-readout 1")
    await asyncio.sleep(0.05)

    abort = await actor.invoke_mock_command("abort")
    await abort

    assert abort.status.did_fail


async def test_expose_abort_flush(delegate, actor: ArchonActor, mocker):
    await actor.invoke_mock_command("expose --no-readout 1")
    await asyncio.sleep(0.05)

    abort = await actor.invoke_mock_command("abort --flush")
    await abort

    assert abort.status.did_succeed


async def test_expose_abort_flush_fails(delegate, actor: ArchonActor, mocker):
    mocker.patch.object(actor.controllers["sp1"], "flush", side_effect=ArchonError)

    await actor.invoke_mock_command("expose --no-readout 1")
    await asyncio.sleep(0.05)

    abort = await actor.invoke_mock_command("abort --flush")
    await abort

    assert abort.status.did_fail


async def test_expose_set_window(delegate, actor: ArchonActor):
    controller = actor.controllers["sp1"]

    await controller.reset_window()
    assert controller.default_window == controller.current_window

    await controller.set_window(lines=100, pixels=100)

    command = await actor.invoke_mock_command("expose 0.01")
    await command

    assert command.status.did_succeed

    filename = delegate.actor.model["filenames"].value[0]
    hdu = fits.open(filename)
    assert hdu[0].data.shape == (200, 200)


async def test_expose_with_dark(delegate, actor: ArchonActor, mocker):
    expose_mock = mocker.patch.object(delegate, "expose", return_value=True)
    mocker.patch.object(delegate, "readout", return_value=True)

    command = await actor.invoke_mock_command("expose --with-dark 0.01")
    await command

    assert command.status.did_succeed

    expose_mock.assert_called()
    assert expose_mock.call_count == 2


async def test_expose_with_dark_no_readout_fails(delegate, actor: ArchonActor):
    command = await actor.invoke_mock_command("expose --with-dark --no-readout 0.01")
    await command

    assert command.status.did_fail
    assert command.replies[-1].message == {
        "error": "--with-dark cannot be used with --no-readout."
    }
