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

from ..tools import check_controller, controller
from . import parser


__all__ = ["expose", "read", "abort"]


@parser.command()
@controller
@click.argument(
    "EXPOSURE-TIME",
    type=float,
    nargs=1,
    required=False,
)
@click.option(
    "--window-mode",
    type=str,
    help="Exposure window profile.",
)
@click.option(
    "--bias",
    "flavour",
    flag_value="bias",
    default=False,
    show_default=True,
    help="Take a bias.",
)
@click.option(
    "--dark",
    "flavour",
    flag_value="dark",
    default=False,
    help="Take a dark.",
)
@click.option(
    "--flat",
    "flavour",
    flag_value="flat",
    default=False,
    help="Take a flat.",
)
@click.option(
    "--arc",
    "flavour",
    flag_value="arc",
    default=False,
    help="Take an arc.",
)
@click.option(
    "--object",
    "flavour",
    flag_value="object",
    default=True,
    help="Take an object frame.",
)
@click.option(
    "--readout/--no-readout",
    " /-R",
    default=True,
    help="Whether to read out the frame.",
)
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
@click.option(
    "-n",
    "--count",
    type=int,
    default=1,
    help="Number of images to take.",
)
@click.option(
    "--no-write",
    "-W",
    is_flag=True,
    help="Do not write image after reading.",
)
@click.option(
    "--no-shutter",
    is_flag=True,
    help="Do not trigger the shutter.",
)
@click.option(
    "--with-dark",
    is_flag=True,
    help="Take a matching dark exposure.",
)
async def expose(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: dict[str, ArchonController],
    exposure_time: float | None = None,
    window_mode: str | None = None,
    controller: str | None = None,
    flavour: str = "object",
    readout: bool = True,
    header: str = "{}",
    delay_readout: int = 0,
    count: int = 1,
    no_shutter: bool = False,
    with_dark: bool = False,
    no_write: bool = False,
):
    """Exposes the cameras."""

    assert command.actor

    selected_controllers: list[ArchonController]

    if with_dark and not readout:
        return command.fail("--with-dark cannot be used with --no-readout.")

    if not controller:
        selected_controllers = list(controllers.values())
    else:
        if controller not in controllers:
            return command.fail(error=f"Controller {controller!r} not found.")
        selected_controllers = [controllers[controller]]

    if not all([check_controller(command, c) for c in selected_controllers]):
        return command.fail()

    delegate = command.actor.expose_delegate
    if delegate is None:
        return command.fail(error="Cannot find expose delegate.")

    extra_header = json.loads(header)

    if count > 1 and readout is False:
        return command.fail(error="--count > 1 requires readout.")

    for n in range(1, count + 1):

        flavours = [flavour, "dark"] if with_dark else [flavour]
        for this_flavour in flavours:

            delegate.use_shutter = not no_shutter
            result = await delegate.expose(
                command,
                selected_controllers,
                flavour=this_flavour,
                exposure_time=exposure_time,
                readout=readout,
                extra_header=extra_header,
                delay_readout=delay_readout,
                window_mode=window_mode,
                write=not no_write,
            )

            if not result:
                # expose will fail the command.
                return

    return command.finish()


@parser.command()
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
async def read(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: Dict[str, ArchonController],
    header: str,
    delay_readout: int,
):
    """Finishes the ongoing exposure."""

    assert command.actor

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


@parser.command()
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

    assert command.actor

    if all_:
        force = True

    expose_data = command.actor.expose_delegate.expose_data

    if expose_data is None:
        if force:
            command.warning(error="No exposure found.")
        else:
            return command.fail(error="No exposure found.")

    scontr: list[ArchonController]
    if all_ or not expose_data:
        scontr = list(controllers.values())
    else:
        scontr = expose_data.controllers

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
