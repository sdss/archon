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

from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError

from ..tools import check_controller, controller_list, error_controller, open_with_lock
from . import parser


async def _do_one_controller(
    command: Command,
    controller: ArchonController,
    exposure_params: dict[str, Any],
    exp_no: int,
    mjd_dir: pathlib.Path,
) -> bool:
    """Does the heavy lifting of exposing and writing a single controller."""

    config = command.actor.config
    path: pathlib.Path = mjd_dir / config["files"]["template"]
    file_path = str(path.absolute()).format(
        exposure_no=exp_no,
        controller=controller.name,
    )

    exp_time = exposure_params["exposure_time"]

    command.debug(
        controller_message=dict(
            controller=controller.name,
            text="Starting exposure sequence "
            "(flavour={flavour!r}, exp_time={exposure_time}).".format(
                **exposure_params
            ),
        )
    )

    # Get initial frame buffer info
    frame_info_bef = await controller.get_frame()

    # Hold timing, just in case
    await controller.send_command("HOLDTIMING", timeout=2)

    # Set exposure params
    await controller.set_param("Exposures", 1)
    await controller.set_param("IntMS", int(exp_time * 1000))

    # Open shutter (placeholder)

    # Release timing
    command.debug(
        controller_message=dict(
            controller=controller.name,
            text="Start exposing",
        )
    )
    await controller.send_command("RELEASETIMING", timeout=1)

    # Wait until the exposure is complete
    await asyncio.sleep(exp_time)

    # Close shutter (placeholder)

    # Wait a little bit and check that we are reading out to a new buffer
    await asyncio.sleep(1)

    # Get new frame info
    frame_info_aft = await controller.get_frame()

    wbuf_bef = frame_info_bef["wbuf"]
    wbuf = frame_info_aft["wbuf"]
    if wbuf == wbuf_bef or frame_info_aft[f"buf{wbuf}complete"] == 1:
        error_controller(command, controller, "Readout failed to start.")
        await controller.send_command("HOLDTIMING", timeout=1)
        raise ArchonError("Failed reading out.")

    wbuf = frame_info_aft["wbuf"]
    command.debug(
        controller_message=dict(
            controller=controller.name,
            text=f"Readout started on buffer {wbuf}.",
        )
    )

    # Wait a reasonable time and then start checking the buffer for completion.
    ro_exp = config["timeouts"]["readout_expected"]
    await asyncio.sleep(ro_exp)
    ro_elapsed = ro_exp
    while True:
        frame_info = await controller.get_frame()
        if frame_info[f"buf{wbuf}complete"] == 1:
            break
        if ro_elapsed > config["timeouts"]["readout_max"]:
            error_controller(
                command,
                controller,
                "Timed out while waiting for readout to complete.",
            )
            await controller.send_command("HOLDTIMING", timeout=1)
            raise ArchonError("Failed reading out.")
        await asyncio.sleep(1.0)  # Sleep for one second before asking again.
        ro_elapsed += 1

    # Fetch buffer data
    command.debug(
        controller_message=dict(
            controller=controller.name,
            text=f"Fetching buffer {wbuf}.",
        )
    )
    await controller.send_command("HOLDTIMING", timeout=1)
    data = await controller.fetch(wbuf)

    # Divide array into CCDs and create FITS.
    # TODO: add at least a placeholder header with some basics.
    command.debug(
        controller_message=dict(
            controller=controller.name,
            text="Saving data to disk.",
        )
    )

    loop = asyncio.get_running_loop()
    ccd_info = config["controllers"][controller.name]["ccds"]
    fits = fitsio.FITS(file_path, "rw")
    for ccd_name in ccd_info:
        region = ccd_info[ccd_name]
        ccd_data = data[region[1] : region[3], region[0] : region[2]]
        fits_write = partial(fits.create_image_hdu, extname=ccd_name)
        await loop.run_in_executor(None, fits_write, ccd_data)
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
    default=True,
    show_default=True,
    help="Take a bias",
)
@click.option(
    "--dark",
    "flavour",
    flag_value="dark",
    default=True,
    help="Take a dark",
)
@click.option(
    "--flat",
    "flavour",
    flag_value="flat",
    default=True,
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
    command: Command,
    controllers: dict[str, ArchonController],
    exposure_time: float,
    controller_list: Optional[tuple[str]],
    flavour: Optional[str],
):
    """Exposes the cameras."""

    if controller_list is None:
        selected_controllers = list(controllers.values())
    else:
        selected_controllers: list[ArchonController] = []
        for cname in controller_list:
            if cname not in controllers:
                return command.fail(error=f"Controller {cname!r} not found.")
            selected_controllers.append(controllers[cname])

    if not all([check_controller(command, c) for c in selected_controllers]):
        return command.fail()

    if flavour == "bias":
        exposure_time = 0.0
    else:
        if exposure_time is None:
            return command.fail(
                error=f"Exposure time required for exposure of flavour {flavour!r}."
            )
    exposure_params = {"exposure_time": exposure_time, "flavour": flavour}

    try:
        result = await _do_exposures(command, selected_controllers, exposure_params)
    except ArchonError as err:
        return command.fail(error=str(err))

    if result:
        return command.finish()
    else:
        return command.fail()
