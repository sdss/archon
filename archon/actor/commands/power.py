#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-04-12
# @Filename: power.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from archon.controller.command import ArchonCommand
from archon.exceptions import ArchonError

from ..tools import error_controller, parallel_controllers
from . import parser


if TYPE_CHECKING:
    from archon.actor import ArchonCommandType
    from archon.controller.controller import ArchonController


@parser.command()
@click.argument("MODE", type=click.Choice(["on", "off"]))
@parallel_controllers()
async def power(command: ArchonCommandType, controller: ArchonController, mode: str):
    """Powers on/off a controller."""

    try:
        status = await controller.get_device_status()
    except ArchonError as ee:
        return error_controller(command, controller, str(ee))

    power_status = status["power"]
    if power_status not in [2, 4]:
        return error_controller(
            command,
            controller,
            f"Controller reports unsafe power status {power_status}",
        )

    if power_status == 2 and mode == "off":
        command.info(
            text={"controller": controller.name, "text": "Controller is already off."}
        )
        return True

    if power_status == 4 and mode == "on":
        command.info(
            text={"controller": controller.name, "text": "Controller is already on."}
        )
        return True

    if mode == "off":
        archon_command = "POWEROFF"
    else:
        archon_command = "POWERON"

    acmd: ArchonCommand = await controller.send_command(archon_command, timeout=10)
    if not acmd.succeeded():
        return error_controller(
            command,
            controller,
            f"Failed while powering ({acmd.status.name})",
        )

    if mode == "on":
        await controller.reset()
        if not command.actor.timed_commands.running:
            command.actor.timed_commands.start()

    await command.send_command("archon", f"status -c {controller.name}")

    return True
