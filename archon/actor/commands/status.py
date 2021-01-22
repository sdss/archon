#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: status.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from clu.command import Command

from archon.controller.controller import ArchonController

from ..tools import check_controller, error_controller, parallel_controllers
from . import parser


def check_int(s):
    if s[0] in ("-", "+"):
        return s[1:].isdigit()
    return s.isdigit()


@parser.command()
@parallel_controllers()
async def status(command: Command, controller: ArchonController):
    """Reports the status of the controller."""
    if not check_controller(command, controller):
        return

    cmd = await controller.send_command("STATUS", timeout=1)
    if cmd.status != cmd.status.DONE:
        error_controller(
            command,
            controller,
            f"Command finished with status {cmd.status.name!r}",
        )
        return

    keywords = str(cmd.replies[0].reply).split()
    status = {
        key.lower(): int(value) if check_int(value) else float(value)
        for (key, value) in map(lambda k: k.split("="), keywords)
    }

    command.info(
        status={
            "controller": controller.name,
            **status,
        }
    )
