#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-27
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import os
import pathlib
from contextlib import suppress
from functools import partial

from typing import Any, Optional

import astropy.time
import click
import fitsio
from clu.command import Command

import archon.actor
from archon import config
from archon.controller.controller import ArchonController
from archon.controller.maskbits import ControllerStatus
from archon.exceptions import ArchonError

from ..tools import check_controller, controller_list, open_with_lock
from . import parser

__all__ = ["expose"]


async def get_header(
    command: Command[archon.actor.ArchonActor],
    controller: ArchonController,
    exposure_params: dict[str, Any],
):
    """Returns the header of the FITS file."""

    header = {}

    header["SPEC"] = controller.name
    header["OBSTIME"] = astropy.time.Time.now().isot
    header["EXPTIME"] = exposure_params["exposure_time"]
    header["IMAGETYP"] = exposure_params["flavour"]

    # Connects to the H5179 device and gets the lab temperature and humidity.
    try:
        h5179 = config["sensors"]["H5179"]
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(h5179["host"], h5179["port"]),
            timeout=2,
        )
        writer.write(b"status\n")
        data = await asyncio.wait_for(reader.readline(), timeout=1)
        temp, hum, __, last = data.decode().strip().split()

        temp = float(temp)
        hum = float(hum)

        last_seen = astropy.time.Time(last, format="isot")
        delta = astropy.time.Time.now() - last_seen
        if delta.datetime.seconds / 60 > 10:
            raise RuntimeError("Lab metrology is over 10 minutes old.")

    except BaseException as err:
        command.warning(text=f"Failed retriving H5179 data: {err}")
        temp = -999.0
        hum = -999.0

    header["LABTEMP"] = temp
    header["LABHUMID"] = hum

    return header


async def _do_one_controller(
    command: Command[archon.actor.ArchonActor],
    controller: ArchonController,
    exposure_params: dict[str, Any],
    exp_no: int,
    mjd_dir: pathlib.Path,
) -> bool:
    """Does the heavy lifting of exposing and writing a single controller."""

    observatory = command.actor.observatory.lower()
    hemisphere = "n" if observatory == "apo" else "s"

    config = command.actor.config
    path: pathlib.Path = mjd_dir / config["files"]["template"]
    file_path = str(path.absolute()).format(
        exposure_no=exp_no,
        controller=controller.name,
        observatory=observatory,
        hemisphere=hemisphere,
    )

    exp_time = exposure_params["exposure_time"]

    command.debug(
        text=dict(
            controller=controller.name,
            text="Starting exposure sequence "
            "(flavour={flavour!r}, exp_time={exposure_time}).".format(
                **exposure_params
            ),
        )
    )

    # Start integration.
    await controller.integrate(exposure_time=exp_time)

    # Open shutter (placeholder)

    # Wait until the exposure is complete.
    # TODO: Here we should take into account the network and mechanical delay in
    # opening the shutter.
    await asyncio.sleep(exp_time)

    # Close shutter (placeholder)

    # Wait a little bit and check that we are reading out to a new buffer
    await asyncio.sleep(0.1)

    # Get new frame info
    frame_info = await controller.get_frame()
    wbuf = frame_info["wbuf"]
    if frame_info[f"buf{wbuf}complete"] != 0:
        controller.status = ControllerStatus.ERROR
        raise ArchonError("Read-out failed to start.")

    controller.status = ControllerStatus.READING
    command.debug(
        text=dict(
            controller=controller.name,
            text=f"Reading frame into buffer {wbuf}.",
        )
    )
    # Wait until buffer is complete.
    elapsed = 0
    while True:
        frame_info = await controller.get_frame()
        if frame_info[f"buf{wbuf}complete"] == 1:
            break
        if elapsed > config["timeouts"]["readout_max"]:
            controller.status = ControllerStatus.ERROR
            raise ArchonError("Timed out waiting for read-out to finish.")
        await asyncio.sleep(1.0)  # Sleep for one second before asking again.
        elapsed += 1

    # Reset timing
    await controller.reset()

    # Fetch buffer data
    command.debug(
        text=dict(
            controller=controller.name,
            text=f"Fetching buffer {wbuf}.",
        )
    )
    data = await controller.fetch(wbuf)

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
    fits = fitsio.FITS(file_path, "rw")
    header = await get_header(command, controller, exposure_params)
    for ccd_name in ccd_info:
        region = ccd_info[ccd_name]
        ccd_data = data[region[1] : region[3], region[0] : region[2]]
        header_ccd = header.copy()
        header_ccd["CCD"] = ccd_name
        fits_write = partial(fits.create_image_hdu, extname=ccd_name, header=header_ccd)
        await loop.run_in_executor(None, fits_write, ccd_data)
        fits[-1].write_keys(header_ccd)
    await loop.run_in_executor(None, fits.close)

    command.info(text=f"File {os.path.basename(file_path)} written to disk.")

    return True


async def _do_exposures(
    command: Command,
    controllers: list[ArchonController],
    exposure_params: dict[str, Any],
) -> bool:
    """Manages exposing several controllers."""

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

    try:
        with open_with_lock(next_exp_file, "r+") as fd:
            fd.seek(0)
            data = fd.read().strip()
            next_exp_no: int = int(data) if data != "" else 1

            _jobs: list[asyncio.Task] = []
            for controller in controllers:
                _jobs.append(
                    asyncio.create_task(
                        _do_one_controller(
                            command,
                            controller,
                            exposure_params,
                            next_exp_no,
                            mjd_dir,
                        )
                    )
                )

            try:
                results = await asyncio.gather(*_jobs, return_exceptions=False)
            except BaseException as err:
                command.error(error=str(err))
                command.error("One controller failed. Cancelling remaining tasks.")
                for job in _jobs:
                    if not job.done():
                        with suppress(asyncio.CancelledError):
                            job.cancel()
                            await job
                return False

            if not all(results):
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


@parser.command()
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
async def expose(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: dict[str, ArchonController],
    exposure_time: float,
    controller_list: Optional[tuple[str]],
    flavour: Optional[str],
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

    if command.actor._exposing:
        return command.fail("The actor is already exposing.")

    if flavour == "bias":
        exposure_time = 0.0
    else:
        if exposure_time is None:
            return command.fail(
                error=f"Exposure time required for exposure of flavour {flavour!r}."
            )
    exposure_params = {"exposure_time": exposure_time, "flavour": flavour}

    try:
        command.actor._exposing = True
        result = await _do_exposures(command, selected_controllers, exposure_params)
    except ArchonError as err:
        command.actor._exposing = False
        return command.fail(error=str(err))

    command.actor._exposing = False

    if result:
        return command.finish()
    else:
        return command.fail()
