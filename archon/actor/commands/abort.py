#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-30
# @Filename: abort.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from clu.command import Command

from archon.actor.commands import parser
from archon.actor.tools import check_controller, error_controller, parallel_controllers
from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError


@parser.command()
@parallel_controllers()
async def abort(command: Command, controller: ArchonController):
    """Aborts ongoing exposures."""
    if not check_controller(command, controller):
        return

    try:
        await controller.reset()
    except ArchonError as ee:
        return error_controller(command, controller, str(ee))

    return True
