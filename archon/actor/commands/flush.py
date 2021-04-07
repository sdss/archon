#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-04-06
# @Filename: flush.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from clu.command import Command

from archon.controller.controller import ArchonController
from archon.exceptions import ArchonControllerError, ArchonError

from ..tools import check_controller, error_controller, parallel_controllers
from . import parser


@parser.command()
@parallel_controllers()
async def flush(command: Command, controller: ArchonController):
    """Flushes controllers."""

    if not check_controller(command, controller):
        return False

    try:
        await controller.reset()
        await controller.flush(force=True)
    except (ArchonControllerError, ArchonError) as err:
        return error_controller(command, controller, f"Failed flushing: {err}")

    return True
