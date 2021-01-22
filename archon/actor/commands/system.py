#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: system.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import re

from clu.command import Command

from archon.controller.controller import ArchonController
from archon.controller.maskbits import ModType

from ..tools import check_controller, error_controller, parallel_controllers
from . import parser


@parser.command()
@parallel_controllers()
async def system(command: Command, controller: ArchonController):
    """Reports the status of the controller backplane."""
    if not check_controller(command, controller):
        return

    cmd = await controller.send_command("SYSTEM", timeout=1)
    if cmd.status != cmd.status.DONE:
        error_controller(
            command,
            controller,
            f"Command finished with status {cmd.status.name!r}",
        )
        return

    keywords = str(cmd.replies[0].reply).split()
    system = {}
    for (key, value) in map(lambda k: k.split("="), keywords):
        system[key.lower()] = value
        if match := re.match(r"^MOD([0-9]{1,2})_TYPE", key, re.IGNORECASE):
            name_key = f"mod{match.groups()[0]}_name"
            system[name_key] = ModType(int(value)).name

    command.info(
        system={
            "controller": controller.name,
            **system,
        }
    )
