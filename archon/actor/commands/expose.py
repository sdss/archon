#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-27
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


import pathlib

from typing import Optional

import astropy.time
import click
from clu.command import Command

from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError

from ..tools import check_controller, controller_list, open_with_lock
from . import parser


async def _do_exposures(
    command: Command,
    controllers: list[ArchonController],
    mjd: int,
    exposure_no: int,
) -> bool:
    """Does the heavy lifting of exposing multiple controllers."""

    return True


@parser.command()
@click.argument("EXPOSURE-TIME", type=float, required=False)
@controller_list
@click.option("--flavour", "-f", type=click.Choice(["bias", "dark", "flat", "object"]))
async def expose(
    command: Command,
    controllers: dict[str, ArchonController],
    exposure_time: float,
    controller_list: tuple[str],
    flavour: Optional[str],
):
    """Exposures the cameras for EXPOSURE-TIME seconds."""

    if controller_list == ():
        selected_controllers = list(controllers.values())
    else:
        selected_controllers: list[ArchonController] = []
        for cname in controller_list:
            if cname not in controllers:
                return command.fail(error=f"Controller {cname!r} not found.")
            selected_controllers.append(controllers[cname])

    if not all([check_controller(command, c) for c in selected_controllers]):
        return command.fail()

    now = astropy.time.Time.now()
    mjd = int(now.mjd)

    data_dir = pathlib.Path(command.actor.config["files"]["data_dir"])
    if not data_dir.exists():
        data_dir.mkdir(parents=True)

    next_exp_file = data_dir / "nextExposureNumber"
    if not next_exp_file.exists():
        next_exp_file.touch()

    try:
        with open_with_lock(next_exp_file, "r+") as fd:
            fd.seek(0)
            data = fd.read().strip()
            next_exp_no: int = int(data) if data != "" else 1
            await _do_exposures(command, selected_controllers, mjd, next_exp_no)
    except BlockingIOError:
        return command.fail(
            error="The nextExposureNumber file is locked. This probably "
            "indicates that another spectrograph process is running."
        )
    except ArchonError as err:
        return command.fail(error=str(err))
