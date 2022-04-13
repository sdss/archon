#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-06
# @Filename: test_delegate.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os

from typing import Any

import numpy
import pytest
from astropy.io import fits
from clu import Command

from archon.actor.actor import ArchonActor
from archon.actor.delegate import ExposureDelegate
from archon.controller import ControllerStatus as CS
from archon.exceptions import ArchonError


pytestmark = [pytest.mark.asyncio]


@pytest.mark.parametrize("flavour", ["bias", "dark", "object"])
async def test_delegate_expose(delegate: ExposureDelegate, flavour: str):

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour=flavour,
        exposure_time=0.01,
        readout=True,
    )

    assert result

    assert delegate.actor.model and delegate.actor.model["filename"] is not None

    filename = delegate.actor.model["filename"].value
    assert os.path.exists(filename)

    hdu: Any = fits.open(filename)
    assert hdu[0].data.shape == (2048, 2068)
    assert hdu[0].header["CCDTEMP1"] == -110


async def test_delegate_expose_split_mode(delegate: ExposureDelegate, mocker):

    # For framemode=top
    mocker.patch.object(
        delegate.actor.controllers["sp1"],
        "fetch",
        return_value=numpy.ones((2048 * 2, 2068 * 3)),
    )

    delegate.actor.config["controllers"]["sp1"]["parameters"]["framemode"] = "split"

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=0.01,
        readout=True,
    )

    assert result

    filename = delegate.actor.model["filename"].value
    assert os.path.exists(filename)

    hdu: Any = fits.open(filename)
    assert hdu[0].data.shape == (2048, 2068)
    assert hdu[0].header["CCDTEMP1"] == -110


async def test_delegate_expose_locked(delegate: ExposureDelegate):

    await delegate.lock.acquire()

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=0.01,
        readout=True,
    )

    assert result is False


async def test_delegate_shutter_fails(delegate: ExposureDelegate, mocker):

    mocker.patch.object(delegate, "shutter", return_value=False)

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=0.01,
        readout=True,
    )

    assert result is False


async def test_delegate_fetch_fails(delegate: ExposureDelegate, mocker):

    mocker.patch.object(delegate, "fetch_hdus", side_effect=ArchonError)

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=0.01,
        readout=True,
    )

    assert result is False


async def test_delegate_expose_no_exptime(delegate: ExposureDelegate):

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=None,
        readout=True,
    )

    assert result is False


@pytest.mark.parametrize("status", [CS.EXPOSING, CS.READOUT_PENDING, CS.ERROR])
async def test_delegate_check_expose_fails(delegate: ExposureDelegate, status: CS):

    delegate.actor.controllers["sp1"]._status = status

    command = Command("", actor=delegate.actor)

    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=0.01,
        readout=True,
    )

    assert result is False


async def test_delegate_expose_fails(delegate: ExposureDelegate, mocker):

    mocker.patch.object(
        delegate.actor.controllers["sp1"],
        "expose",
        side_effect=ArchonActor,
    )

    command = Command("", actor=delegate.actor)

    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=1,
        readout=True,
    )

    assert result is False


async def test_delegate_readout_not_locked(delegate: ExposureDelegate):

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=0.01,
        readout=False,
    )
    assert result is True

    delegate.lock.release()

    result = await delegate.readout(command)
    assert result is False


async def test_delegate_readout_no_expose_data(delegate: ExposureDelegate):

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=0.01,
        readout=False,
    )
    assert result is True

    delegate.expose_data = None

    result = await delegate.readout(command)
    assert result is False


async def test_delegate_readout_shutter_fails(delegate: ExposureDelegate, mocker):

    command = Command("", actor=delegate.actor)
    result = await delegate.expose(
        command,
        [delegate.actor.controllers["sp1"]],
        flavour="object",
        exposure_time=0.01,
        readout=False,
    )
    assert result is True

    mocker.patch.object(delegate, "shutter", return_value=False)

    result = await delegate.readout(command)
    assert result is False
