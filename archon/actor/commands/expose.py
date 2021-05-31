#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-27
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import json

from typing import Dict

import click
from clu.command import Command

import archon.actor
from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError

from ..tools import check_controller, controller_list
from . import parser


__all__ = ["expose"]


@parser.group()
def expose(*args):
    """Exposes the cameras."""

    pass


@expose.command()
@controller_list
@click.argument("EXPOSURE-TIME", type=float, nargs=1, required=False)
@click.option(
    "--bias",
    "flavour",
    flag_value="bias",
    default=False,
    show_default=True,
    help="Take a bias",
)
@click.option(
    "--dark",
    "flavour",
    flag_value="dark",
    default=False,
    help="Take a dark",
)
@click.option(
    "--flat",
    "flavour",
    flag_value="flat",
    default=False,
    help="Take a flat",
)
@click.option(
    "--object",
    "flavour",
    flag_value="object",
    default=True,
    help="Take an object frame",
)
@click.option(
    "--finish",
    "-f",
    "do_finish",
    is_flag=True,
    help="Finish the exposure",
)
async def start(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: dict[str, ArchonController],
    exposure_time: float,
    controller_list: tuple[str, ...],
    flavour: str,
    do_finish: bool,
):
    """Exposes the cameras."""

    selected_controllers: list[ArchonController]

    if len(controller_list) == 0:
        selected_controllers = list(controllers.values())
    else:
        selected_controllers = []
        for cname in controller_list:
            if cname not in controllers:
                return command.fail(error=f"Controller {cname!r} not found.")
            selected_controllers.append(controllers[cname])

    if not all([check_controller(command, c) for c in selected_controllers]):
        return command.fail()

    delegate = command.actor.expose_delegate
    if delegate is None:
        return command.fail(error="Cannot find expose delegate.")

    result = await delegate.expose(
        command,
        selected_controllers,
        flavour=flavour,
        exposure_time=exposure_time,
        readout=do_finish,
    )

    if result:
        return command.finish()
    else:
        # expose will fail the command.
        return


@expose.command()
@click.option(
    "--header",
    type=str,
    default="{}",
    help="JSON string with additional header keyword-value pairs. Avoid using spaces.",
)
@click.option(
    "-d",
    "--delay-readout",
    type=int,
    default=0,
    help="Slow down the readout by this many seconds.",
)
async def finish(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: Dict[str, ArchonController],
    header: str,
    delay_readout: int,
):
    """Finishes the ongoing exposure."""

    delegate = command.actor.expose_delegate
    if delegate is None:
        return command.fail(error="Cannot find expose delegate.")

    extra_header = json.loads(header)

    result = await delegate.readout(
        command,
        extra_header=extra_header,
        delay_readout=delay_readout,
    )

    if result is True:
        return command.finish()
    else:
        return


@expose.command()
@click.option("--flush", is_flag=True, help="Flush the device after aborting.")
@click.option("--force", is_flag=True, help="Forces abort.")
@click.option("--all", "all_", is_flag=True, help="Aborts all the controllers.")
async def abort(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: dict[str, ArchonController],
    flush: bool,
    force: bool,
    all_: bool,
):
    """Aborts the exposure."""

    if all_:
        force = True

    exposure_data = command.actor.expose_delegate.exposure_data

    if exposure_data is None:
        if force:
            command.warning(error="No exposure found.")
        else:
            return command.fail(error="No exposure found.")

    scontr: list[ArchonController]
    if all_ or not exposure_data:
        scontr = list(controllers.values())
    else:
        scontr = exposure_data.controllers

    command.debug(text="Aborting exposures")
    try:
        await asyncio.gather(*[contr.abort(readout=False) for contr in scontr])
    except ArchonError as err:
        return command.fail(error=f"Failed aborting exposures: {err}")

    if flush:
        command.debug(text="Flushing devices")
        try:
            await asyncio.gather(*[contr.flush() for contr in scontr])
        except ArchonError as err:
            return command.fail(error=f"Failed flushing devices: {err}")

    command.actor.expose_delegate.reset()

    return command.finish()
