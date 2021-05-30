#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-26
# @Filename: init.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import os

from clu.command import Command

import archon
from archon.controller.command import ArchonCommand
from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError

from ..tools import check_controller, error_controller, parallel_controllers
from . import parser


def _output(
    command: Command,
    controller: ArchonController,
    text: str,
    message_code="d",
):
    command.write(
        message_code=message_code,
        text=dict(
            controller=controller.name,
            text=text,
        ),
    )


@parser.command()
@parallel_controllers()
async def init(command: Command, controller: ArchonController):
    """Initialises a controller."""

    if not check_controller(command, controller):
        return

    # Load config, apply all, LOADPARAMS, and LOADTIMING, but no power up.
    _output(command, controller, "Loading and applying config", "i")

    configuration_file: str = command.actor.config["archon_config_file"]
    archon_etc = os.path.join(os.path.dirname(__file__), "../../etc")
    configuration_file = configuration_file.format(archon_etc=archon_etc)
    if not os.path.isabs(configuration_file):
        archon_root = os.path.dirname(os.path.realpath(archon.__file__))
        configuration_file = os.path.join(archon_root, configuration_file)

    try:
        await controller.write_config(configuration_file, applyall=True, poweron=False)
    except ArchonError as err:
        return error_controller(command, controller, str(err))

    # Set parameters
    _output(command, controller, "Setting initial parameters")
    initial_params = {"Exposures": 0, "ReadOut": 0, "DoFlush": 0}
    for (param, value) in initial_params.items():
        try:
            await controller.set_param(param, value)
        except ArchonError as err:
            return error_controller(command, controller, str(err))

    # Unlock all buffers
    _output(command, controller, "Unlocking buffers")
    acmd: ArchonCommand = await controller.send_command("LOCK0", timeout=5)
    if not acmd.succeeded():
        return error_controller(
            command,
            controller,
            f"Failed while unlocking frame buffers ({acmd.status.name})",
        )

    # Power on
    _output(command, controller, "Powering on")
    acmd: ArchonCommand = await controller.send_command("POWERON", timeout=10)
    if not acmd.succeeded():
        return error_controller(
            command,
            controller,
            f"Failed while powering on ({acmd.status.name})",
        )

    await asyncio.sleep(1)
    await controller.reset()

    return True
