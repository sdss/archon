#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-04-06
# @Filename: test_flush.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from unittest.mock import AsyncMock

import pytest

from archon.controller.controller import ArchonController
from archon.controller.maskbits import ControllerStatus
from archon.exceptions import ArchonControllerError


pytestmark = [pytest.mark.asyncio]


async def test_flush(controller: ArchonController, mocker):
    set_param_mock: AsyncMock = mocker.patch.object(
        ArchonController,
        "set_param",
        wraps=controller.set_param,
    )
    controller.status = ControllerStatus.EXPOSING

    await controller.flush(wait_for=0.01)

    set_param_mock.assert_any_call("DoFlush", 1)

    assert controller.status == ControllerStatus.IDLE
