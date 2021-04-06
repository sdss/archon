#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-30
# @Filename: test_expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from unittest.mock import AsyncMock

import pytest

from archon.controller.controller import ArchonController
from archon.controller.maskbits import ControllerStatus
from archon.exceptions import ArchonControllerError

pytestmark = [pytest.mark.asyncio]


async def test_expose(controller: ArchonController, mocker):
    set_param_mock: AsyncMock = mocker.patch.object(
        ArchonController,
        "set_param",
        wraps=controller.set_param,
    )
    await controller.expose(2)
    set_param_mock.assert_any_call("Exposures", 1)
    set_param_mock.assert_any_call("IntMS", 2000)
    assert controller.status & ControllerStatus.EXPOSING
    assert controller.status & ControllerStatus.READOUT_PENDING


async def test_expose_not_idle(controller: ArchonController):
    controller.status = ControllerStatus.READOUT_PENDING
    with pytest.raises(ArchonControllerError):
        await controller.expose(2)
