#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-22
# @Filename: config.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import configparser
import os
import re

import click
from clu.command import Command

from archon.controller.controller import ArchonController

from ..tools import check_controller
from . import parser

key_value_re = re.compile("^(.+?)=(.*)$")


def parse_line(line):
    k, v = key_value_re.match(line).groups()
    # It seems the GUI replaces / with \ even if that doesn't seem
    # necessary in the INI format.
    k = k.replace("/", "\\")
    return k, v


@parser.group()
def config(*args):
    """Manages the configuration of the device."""
    pass


@config.command()
@click.argument("controller_name", metavar="CONTROLLER")
@click.option(
    "--save",
    "-s",
    is_flag=True,
    help="Saves the configuration to ~/archon_<controller>.acf. "
    "Does not output to console. Overwrites previous files.",
)
@click.option(
    "--full",
    "-f",
    is_flag=True,
    help="Reads all the possible lines. Otherwise reads until two "
    "consecutive empty lines are found.",
)
async def read(
    command: Command,
    controllers: dict[str, ArchonController],
    controller_name: str,
    save: bool,
    full: bool,
):
    """Reads the configuration from the controller."""
    if controller_name not in controllers:
        return command.fail(f"Controller {controller_name!r} does not exist.")

    controller = controllers[controller_name]
    if not check_controller(command, controller):
        return command.fail()

    lines: list[str] = []
    n_blank = 0
    max_lines = 16384
    for n_line in range(max_lines):
        cmd = await controller.send_command(f"RCONFIG{n_line:04X}", timeout=0.1)
        if cmd.status == cmd.status.TIMEDOUT or cmd.status == cmd.status.FAILED:
            return command.fail(
                f"An RCONFIG command returned with code {cmd.status.name!r}"
            )
        if cmd.replies == []:
            return command.fail("An RCONFIG command did not return.")
        reply = str(cmd.replies[0])
        if reply == "" and not full:
            n_blank += 1
        else:
            n_blank = 0
            lines.append(reply)

        if n_blank == 2:
            break

    # Trim possible empty lines at the end.
    config = "\n".join(lines).strip().splitlines()
    if not save:
        return command.finish(config=config)

    # The GUI ACF file includes the system information, so we get it.
    system = await controller.send_command("SYSTEM")
    system_lines = [kw for kw in str(system.replies[0]).split()]

    c = configparser.ConfigParser()
    c.optionxform = str  # Make it case-sensitive
    c.add_section("SYSTEM")
    for sl in system_lines:
        k, v = parse_line(sl)
        c.set("SYSTEM", k, v)
    c.add_section("CONFIG")
    for cl in config:
        k, v = parse_line(cl)
        c.set("CONFIG", k, v)

    path = os.path.expanduser(f"~/archon_{controller.name}.acf")
    with open(path, "w") as f:
        c.write(f)

    return command.finish(text=f"Config written to {path!r}")
