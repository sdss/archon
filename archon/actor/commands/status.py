#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: status.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import click
from clu.command import Command

from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError

from ..tools import check_controller, error_controller, parallel_controllers
from . import parser


@parser.command()
@parallel_controllers()
@click.option("-g", "--geek", is_flag=True, help="Reports additional information.")
async def status(command: Command, controller: ArchonController, geek: bool):
    """Reports the status of the controller."""
    if not check_controller(command, controller):
        return

    if not geek:
        command.info(
            status={
                "controller": controller.name,
                "status": controller.status.name,
            }
        )
        return True

    try:
        status = await controller.get_status()
    except ArchonError as ee:
        return error_controller(command, controller, str(ee))

    command.info(
        status={
            "controller": controller.name,
            "status": controller.status.name,
            **status,
        }
    )

    return True
