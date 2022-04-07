#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-26
# @Filename: init.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import os
import re

from typing import TYPE_CHECKING

import click
from clu.command import Command

import archon
from archon.controller.command import ArchonCommand
from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError

from ..tools import error_controller, parallel_controllers
from . import parser


if TYPE_CHECKING:
    from ..actor import ArchonActor


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
@click.argument("CONFIG-FILE", type=str, required=False)
@click.option("--hdr", is_flag=True, help="Set HDR mode.")
@parallel_controllers()
async def init(
    command: Command[ArchonActor],
    controller: ArchonController,
    config_file: str | None = None,
    hdr=False,
):
    """Initialises a controller."""

    assert command.actor

    # Load config, apply all, LOADPARAMS, and LOADTIMING, but no power up.
    _output(command, controller, "Loading and applying config", "i")

    archon_etc = os.path.join(os.path.dirname(__file__), "../../etc")

    if config_file is None:
        default_config: str = command.actor.config["archon"]["config_file"]
        config_file = default_config.format(archon_etc=archon_etc)

    if not os.path.isabs(config_file):
        archon_root = os.path.dirname(os.path.realpath(archon.__file__))
        config_file = os.path.join(archon_root, config_file)

    if not os.path.exists(config_file):
        return error_controller(command, controller, f"Cannot find file {config_file}")

    data = open(config_file).read()
    if hdr:
        data = re.sub("(SAMPLEMODE)=[01]", "\\1=1", data)

    # Stop timed commands since they may fail while writing data or power is off
    await command.actor.timed_commands.stop()

    try:
        await controller.write_config(data, applyall=True, poweron=False)
        controller.acf_loaded = config_file
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

    await controller.reset()
    if not command.actor.timed_commands.running:
        command.actor.timed_commands.start()

    return True
