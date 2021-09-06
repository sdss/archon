#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-06
# @Filename: test_delegate.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os

from typing import Any

import pytest
from astropy.io import fits
from clu import Command

from archon.actor.actor import ArchonActor
from archon.actor.delegate import ExposureDelegate
from archon.controller import ControllerStatus as CS


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
    assert hdu[0].data.shape == (2048, 2048)


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
