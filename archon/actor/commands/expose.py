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
import os
import pathlib
from contextlib import suppress

from typing import Dict, Optional

import astropy.time
import click
from astropy.io import fits
from clu.command import Command

import archon.actor
from archon.controller.controller import ArchonController
from archon.controller.maskbits import ControllerStatus
from archon.exceptions import ArchonError

from ..tools import check_controller, controller_list, open_with_lock, read_govee
from . import parser

__all__ = ["expose"]


@parser.group()
def expose(*args):
    """Exposes the cameras."""
    pass


@expose.command()
@click.argument("EXPOSURE-TIME", type=float, required=False)
@controller_list
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
async def start(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: dict[str, ArchonController],
    exposure_time: float,
    controller_list: Optional[tuple[str]],
    flavour: str,
):
    """Exposes the cameras."""

    selected_controllers: list[ArchonController]

    if controller_list is None:
        selected_controllers = list(controllers.values())
    else:
        selected_controllers = []
        for cname in controller_list:
            if cname not in controllers:
                return command.fail(error=f"Controller {cname!r} not found.")
            selected_controllers.append(controllers[cname])

    if not all([check_controller(command, c) for c in selected_controllers]):
        return command.fail()

    for controller in selected_controllers:
        cname = controller.name
        if controller.status & ControllerStatus.EXPOSING:
            return command.fail(error=f"Controller {cname} is exposing.")
        elif controller.status & ControllerStatus.READOUT_PENDING:
            return command.fail(
                error=f"Controller {cname} has a read out pending. "
                "Read or flush the device."
            )
        elif controller.status & ControllerStatus.ERROR:
            return command.fail(error=f"Controller {cname} has status ERROR.")

    if flavour == "bias":
        exposure_time = 0.0
    else:
        if exposure_time is None:
            return command.fail(
                error=f"Exposure time required for exposure of flavour {flavour!r}."
            )

    command.actor.expose_data = archon.actor.ExposeData(
        exposure_time=exposure_time, flavour=flavour, controllers=selected_controllers
    )

    try:
        if await _start_controllers(command, selected_controllers):
            return command.finish()
        else:
            return command.fail()
    except ArchonError as err:
        command.actor.expose_data = None
        return command.fail(error=str(err))


@expose.command()
@click.option("--header", type=str, default="{}", help="JSON string with ")
async def finish(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: Dict[str, ArchonController],
    header: str,
):
    """Finishes the ongoing exposure."""

    scontr: list[ArchonController]

    if command.actor.expose_data is None:
        return command.fail(error="No exposure found.")

    scontr = command.actor.expose_data.controllers

    command.actor.expose_data.end_time = astropy.time.Time.now()
    command.actor.expose_data.header = json.loads(header)

    try:
        await asyncio.gather(
            *[
                contr.abort(readout=False)
                for contr in scontr
                if contr.status & ControllerStatus.EXPOSING
            ]
        )
        await asyncio.gather(*[_write_image(command, contr) for contr in scontr])
    except ArchonError as err:
        return command.fail(error=f"Failed reading out: {err}")

    return command.finish()


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

    if command.actor.expose_data is None:
        err = "No exposure found."
        if force:
            command.warning(error=err)
        else:
            return command.fail(error=err)

    scontr: list[ArchonController]
    if all_ or not command.actor.expose_data:
        scontr = list(controllers.values())
    else:
        scontr = command.actor.expose_data.controllers

    command.debug(text="Aborting exposures")
    await asyncio.gather(
        *[contr.abort(readout=False) for contr in scontr],
        return_exceptions=True,
    )

    if flush:
        command.debug(text="Flushing devices")
        await asyncio.gather(
            *[contr.flush() for contr in scontr],
            return_exceptions=True,
        )

    return command.finish()


async def _start_controllers(
    command: Command,
    controllers: list[ArchonController],
) -> bool:
    """Starts exposing several controllers."""

    config = command.actor.config

    now = astropy.time.Time.now()
    mjd = int(now.mjd)

    # Get data directory or create it if it doesn't exist.
    data_dir = pathlib.Path(config["files"]["data_dir"])
    if not data_dir.exists():
        data_dir.mkdir(parents=True)

    # We store the next exposure number in a file at the root of the data directory.
    next_exp_file = data_dir / "nextExposureNumber"
    if not next_exp_file.exists():
        next_exp_file.touch()

    # Get the directory for this MJD or create it.
    mjd_dir = data_dir / str(mjd)
    if not mjd_dir.exists():
        mjd_dir.mkdir(parents=True)

    exposure_time = command.actor.expose_data.exposure_time

    try:
        with open_with_lock(next_exp_file, "r+") as fd:
            fd.seek(0)
            data = fd.read().strip()
            next_exp_no: int = int(data) if data != "" else 1

            command.actor.expose_data.mjd = mjd
            command.actor.expose_data.exposure_no = next_exp_no

            _jobs: list[asyncio.Task] = []
            for controller in controllers:
                _jobs.append(
                    asyncio.create_task(
                        controller.expose(
                            exposure_time + config["timeouts"]["expose_timeout"],
                            readout=False,
                        )
                    )
                )

            try:
                await asyncio.gather(*_jobs, return_exceptions=False)
            except BaseException as err:
                command.error(error=str(err))
                command.error("One controller failed. Cancelling remaining tasks.")
                for job in _jobs:
                    if not job.done():
                        with suppress(asyncio.CancelledError):
                            job.cancel()
                            await job
                return False

            # Increment nextExposureNumber
            # TODO: Should we increase the sequence regardless of whether the exposure
            # fails or not?
            fd.seek(0)
            fd.truncate()
            fd.seek(0)
            fd.write(str(next_exp_no + 1))

    except BlockingIOError:
        command.error(
            error="The nextExposureNumber file is locked. This probably "
            "indicates that another spectrograph process is running."
        )
        return False

    return True


async def get_header(
    command: Command[archon.actor.ArchonActor],
    controller: ArchonController,
):
    """Returns the header of the FITS file."""

    expose_data = command.actor.expose_data

    header = fits.Header()

    header["SPEC"] = controller.name
    header["OBSTIME"] = (expose_data.start_time.isot, "Start of the observation")
    header["EXPTIME"] = expose_data.exposure_time
    header["IMAGETYP"] = expose_data.flavour
    header["INTSTART"] = (expose_data.start_time.isot, "Start of the integration")
    header["INTEND"] = (expose_data.end_time.isot, "End of the integration")

    try:
        temp, hum = await read_govee()
    except BaseException as err:
        command.warning(text=f"Failed retriving H5179 data: {err}")
        temp = -999.0
        hum = -999.0

    header["LABTEMP"] = (temp, "Govee H5179 lab temperature [C]")
    header["LABHUMID"] = (hum, "Govee H5179 lab humidity [%]")

    header.update(expose_data.header)

    return header


async def _write_image(
    command: Command[archon.actor.ArchonActor],
    controller: ArchonController,
) -> bool:
    """Waits for readout to complete, fetches the buffer, and writes the image."""

    # Prepare file path
    observatory = command.actor.observatory.lower()
    hemisphere = "n" if observatory == "apo" else "s"

    config = command.actor.config
    expose_data = command.actor.expose_data

    data_dir = pathlib.Path(config["files"]["data_dir"])
    mjd_dir = data_dir / str(expose_data.mjd)

    path: pathlib.Path = mjd_dir / config["files"]["template"]
    file_path = str(path.absolute()).format(
        exposure_no=expose_data.exposure_no,
        controller=controller.name,
        observatory=observatory,
        hemisphere=hemisphere,
    )

    # Read device
    await controller.readout()

    # Fetch buffer
    data = await controller.fetch()

    # Divide array into CCDs and create FITS.
    # TODO: add at least a placeholder header with some basics.
    command.debug(
        text=dict(
            controller=controller.name,
            text="Saving data to disk.",
        )
    )

    loop = asyncio.get_running_loop()
    ccd_info = config["controllers"][controller.name]["ccds"]
    hdu = fits.HDUList([fits.PrimaryHDU()])
    header = await get_header(command, controller)
    for ccd_name in ccd_info:
        region = ccd_info[ccd_name]
        ccd_data = data[region[1] : region[3], region[0] : region[2]]
        ccd_header = header.copy()
        ccd_header["CCD"] = ccd_name
        hdu.append(fits.ImageHDU(data=ccd_data, header=ccd_header))

    if file_path.endswith(".gz"):
        # Astropy compresses with gzip -9 which takes forever. Instead we compress
        # manually with -1, which is still pretty good.
        await loop.run_in_executor(None, hdu.writeto, file_path[:-3])
        cmd = await asyncio.create_subprocess_exec(
            "gzip",
            "-1",
            file_path[:-3],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await cmd.communicate()
        if cmd.returncode != 0:
            raise ArchonError(f"Failed compressing image {path}")
    else:
        await loop.run_in_executor(None, hdu.writeto, file_path)

    command.info(text=f"File {os.path.basename(file_path)} written to disk.")
    command.debug(filename=file_path)

    return True
