#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-24
# @Filename: frame.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import click
from clu.command import Command

from archon.actor.commands import parser
from archon.actor.tools import check_controller
from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError


@parser.group()
def frame(*args):
    """Interacts with the controller buffer frame."""
    pass


@frame.command()
@click.argument("controller_name", metavar="CONTROLLER")
async def status(
    command: Command,
    controllers: dict[str, ArchonController],
    controller_name: str,
):
    """Reads the frame status."""
    if controller_name not in controllers:
        return command.fail(f"Controller {controller_name!r} does not exist.")

    controller = controllers[controller_name]
    if not check_controller(command, controller):
        return command.fail()

    try:
        frame = await controller.get_frame()
    except ArchonError as err:
        return command.fail(
            controller_message={
                "controller": controller.name,
                "text": err,
            }
        )

    return command.finish(
        frame={
            "controller": controller.name,
            **frame,
        }
    )
