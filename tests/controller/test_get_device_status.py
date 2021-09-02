#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-23
# @Filename: test_get_device_status.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest

from archon.controller.controller import ArchonController, ControllerStatus
from archon.exceptions import ArchonControllerError


pytestmark = [pytest.mark.asyncio]


@pytest.mark.commands([["STATUS", ["<{cid}KEY1=1 KEY2=-2.1 POWERGOOD=1"]]])
async def test_get_device_status(controller: ArchonController):
    status = await controller.get_device_status()
    assert isinstance(status, dict)
    assert len(status) == 3
    assert status["key1"] == 1
    assert status["key2"] == -2.1
    assert controller.status


@pytest.mark.commands([["STATUS", ["<{cid}POWERGOOD=0"]]])
async def test_get_device_status_powerbad(controller: ArchonController):
    await controller.get_device_status()
    assert controller.status & ControllerStatus.POWERBAD


@pytest.mark.commands([["STATUS", ["?{cid}"]]])
async def test_get_device_status_error(controller: ArchonController):
    with pytest.raises(ArchonControllerError):
        await controller.get_device_status()


def test_controller_status_flags():

    flags = ControllerStatus.EXPOSING | ControllerStatus.READOUT_PENDING

    assert ControllerStatus.EXPOSING & flags
    assert ControllerStatus.READOUT_PENDING & flags

    assert ControllerStatus.EXPOSING in flags.get_flags()
    assert ControllerStatus.READOUT_PENDING in flags.get_flags()
