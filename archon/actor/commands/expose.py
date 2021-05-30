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
from functools import reduce

from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Union

import astropy.time
import click
from astropy.io import fits
from clu.command import Command

import archon.actor
from archon.controller.controller import ArchonController
from archon.controller.maskbits import ControllerStatus
from archon.exceptions import ArchonError
from archon.tools import gzip_async

from ..tools import check_controller, controller_list, open_with_lock
from . import parser


__all__ = ["expose"]


Post_process_cb_type = Union[
    Callable[
        [Command, ArchonController, List[fits.PrimaryHDU]],
        Tuple[ArchonController, List[fits.PrimaryHDU]],
    ],
    Callable[
        [Command, ArchonController, List[fits.PrimaryHDU]],
        Coroutine[Tuple[ArchonController, List[fits.PrimaryHDU]], Any, Any],
    ],
]


def annotate(params: Dict[str, Any]):
    """Adds attributes to a function."""

    def wrapper(func):
        for param in params:
            setattr(func, param, params[param])
        return func

    return wrapper


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
        exposure_time=exposure_time,
        flavour=flavour,
        controllers=selected_controllers,
    )

    try:
        if await _start_controllers(command, selected_controllers):
            if do_finish:
                await asyncio.sleep(exposure_time)
                return await finish.callback(command, selected_controllers, "{}", 0)
            return command.finish()
        else:
            return command.fail()
    except ArchonError as err:
        command.actor.expose_data = None
        return command.fail(error=str(err))


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
@annotate({"post_process": None})
async def finish(
    command: Command[archon.actor.actor.ArchonActor],
    controllers: Dict[str, ArchonController],
    header: str,
    delay_readout: int,
):
    """Finishes the ongoing exposure."""

    scontr: list[ArchonController]
    post_process_callback: Optional[Post_process_cb_type] = finish.callback.post_process

    loop = asyncio.get_running_loop()

    if command.actor.expose_data is None:
        return command.fail(error="No exposure found.")

    scontr = command.actor.expose_data.controllers

    command.actor.expose_data.end_time = astropy.time.Time.now()
    command.actor.expose_data.header = json.loads(header)
    command.actor.expose_data.delay_readout = delay_readout

    try:
        await asyncio.gather(
            *[
                contr.abort(readout=False)
                for contr in scontr
                if contr.status & ControllerStatus.EXPOSING
            ]
        )
        hdus = await asyncio.gather(*[_fetch_hdus(command, contr) for contr in scontr])
    except Exception as err:
        return command.fail(error=f"Failed reading out: {err}")

    controller_to_hdus = {scontr[ii]: hdus[ii] for ii in range(len(scontr))}

    if post_process_callback is not None:
        jobs = []
        for controller, hdus in controller_to_hdus.items():
            if asyncio.iscoroutinefunction(post_process_callback):
                jobs.append(post_process_callback(command, controller, hdus))
            else:
                jobs.append(
                    loop.run_in_executor(
                        None,
                        post_process_callback,
                        command,
                        controller,
                        hdus,
                    )
                )
        command.debug(text="Running post-process.")
        controller_to_hdus = dict(await asyncio.gather(*jobs))

    command.debug(text="Saving HDUs.")
    await asyncio.gather(
        *[_write_hdus(command, c, h) for c, h in controller_to_hdus.items()]
    )

    command.actor.expose_data = None

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
        if force:
            command.warning(error="No exposure found.")
        else:
            return command.fail(error="No exposure found.")

    scontr: list[ArchonController]
    if all_ or not command.actor.expose_data:
        scontr = list(controllers.values())
    else:
        scontr = command.actor.expose_data.controllers

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

            flavour = command.actor.expose_data.flavour

            # If the exposure is a bias or dark we don't open the shutter, but
            # otherwise we add an extra timeout to allow for the code that handles the
            # shutter to open and close it and control the exposure time that way.
            if exposure_time == 0.0 or flavour in ["bias", "dark"]:
                etime = 0.0
            else:
                etime = exposure_time + config["timeouts"]["expose_timeout"]

            _jobs: list[asyncio.Task] = []
            for controller in controllers:
                t = asyncio.create_task(controller.expose(etime, readout=False))
                _jobs.append(t)

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
    ccd_name: str,
):
    """Returns the header of the FITS file."""

    expose_data = command.actor.expose_data

    header = fits.Header()

    # Basic header
    header["SPEC"] = controller.name
    header["OBSERVAT"] = command.actor.observatory
    header["OBSTIME"] = (expose_data.start_time.isot, "Start of the observation")
    header["EXPTIME"] = expose_data.exposure_time
    header["IMAGETYP"] = expose_data.flavour
    header["INTSTART"] = (expose_data.start_time.isot, "Start of the integration")
    header["INTEND"] = (expose_data.end_time.isot, "End of the integration")

    header["CCD"] = ccd_name

    actor = command.actor
    model = actor.model
    config = actor.config

    # Add keywords specified in the configuration file.
    sensor = config["controllers"][controller.name]["detectors"][ccd_name]["sensor"]
    if hconfig := config.get("header"):
        for hcommand in hconfig:
            for kname in hconfig[hcommand]:
                kname = kname.upper()
                kconfig = hconfig[hcommand][kname]
                if isinstance(kconfig, dict):
                    if ccd_name not in kconfig:
                        command.warning(
                            text=f"Mapping for keyword {kname} does not "
                            f"specify CCD {ccd_name!r}."
                        )
                        header[kname] = "N/A"
                        continue
                    else:
                        kpath, comment = kconfig[ccd_name]
                elif isinstance(kconfig, list):
                    kpath, comment = kconfig
                else:
                    command.warning(text=f"Invalid keyword format for {kname}.")
                    header[kname] = "N/A"
                    continue
                kpath = kpath.format(sensor=sensor).lower()
                value = dict_get(model, kpath)
                if not value:
                    command.warning(
                        text=f"Cannot find header value {kpath} for {kname}. "
                        f"Issuing command {hcommand!r}"
                    )
                    cmd = await actor.send_command(actor.name, hcommand)
                    await cmd
                    value = dict_get(model, kpath)
                    if not value:
                        command.warning(text=f"Cannot retrieve {kpath}.")
                        value = "N/A"
                header[kname] = (value, comment)

    # Convert JSON lists to tuples or astropy fails.
    for key in expose_data.header:
        if isinstance(expose_data.header[key], list):
            expose_data.header[key] = tuple(expose_data.header[key])

    header.update(expose_data.header)

    return header


async def _fetch_hdus(
    command: Command[archon.actor.ArchonActor],
    controller: ArchonController,
) -> List[fits.PrimaryHDU]:
    """Waits for readout to complete, fetches the buffer, and creates the HDUs."""

    config = command.actor.config
    expose_data = command.actor.expose_data

    # Read device
    await controller.readout(delay=expose_data.delay_readout)

    # Fetch buffer
    data = await controller.fetch()

    ccd_info = config["controllers"][controller.name]["detectors"]
    hdus = []
    for ccd_name in ccd_info:
        area = ccd_info[ccd_name]["area"]
        header = await get_header(command, controller, ccd_name)
        ccd_data = data[area[1] : area[3], area[0] : area[2]]
        hdus.append(fits.PrimaryHDU(data=ccd_data, header=header))

    return hdus


def dict_get(d, k: str | list):
    """Recursive dictionary get."""

    if isinstance(k, str):
        k = k.split(".")

    if d[k[0]].value is None:
        return {}

    return reduce(lambda c, k: c.get(k, {}), k[1:], d[k[0]].value)


async def _write_hdus(
    command: Command[archon.actor.ArchonActor],
    controller: ArchonController,
    hdus: List[fits.PrimaryHDU],
):

    loop = asyncio.get_running_loop()

    expose_data = command.actor.expose_data

    config = command.actor.config

    data_dir = pathlib.Path(config["files"]["data_dir"])
    mjd_dir = data_dir / str(expose_data.mjd)

    path: pathlib.Path = mjd_dir / config["files"]["template"]

    for hdu in hdus:
        ccd = hdu.header["ccd"]
        observatory = str(hdu.header["OBSERVAT"]).lower()
        hemisphere = "n" if observatory == "apo" else "s"

        file_path = str(path.absolute()).format(
            exposure_no=expose_data.exposure_no,
            controller=controller.name,
            observatory=observatory,
            hemisphere=hemisphere,
            ccd=ccd,
        )

        if file_path.endswith(".gz"):
            # Astropy compresses with gzip -9 which takes forever. Instead we compress
            # manually with -1, which is still pretty good.
            await loop.run_in_executor(None, hdu.writeto, file_path[:-3])
            await gzip_async(file_path[:-3], complevel=1)
        else:
            await loop.run_in_executor(None, hdu.writeto, file_path)

        assert os.path.exists(file_path), "Failed writing image to disk."

        command.info(text=f"File {os.path.basename(file_path)} written to disk.")
        command.debug(filename=file_path)

    return
