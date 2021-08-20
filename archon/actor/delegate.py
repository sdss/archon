#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-30
# @Filename: delegate.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import os
import pathlib
from contextlib import suppress
from dataclasses import dataclass, field
from functools import reduce

from typing import TYPE_CHECKING, Any, Dict, Generic, List, TypeVar

import astropy.time
import numpy
from astropy.io import fits

from archon.controller.controller import ArchonController
from archon.controller.maskbits import ControllerStatus
from archon.tools import gzip_async


if TYPE_CHECKING:
    from clu import Command

    from .actor import ArchonActor


Actor_co = TypeVar("Actor_co", bound="ArchonActor", covariant=True)


class ExposureDelegate(Generic[Actor_co]):
    """Handles the exposure workflow."""

    def __init__(self, actor: Actor_co):

        self.actor = actor

        self.exposure_data: ExposeData | None = None
        self.next_exp_file: pathlib.Path | None = None

        self.lock = asyncio.Lock()

        self._command: Command[Actor_co] | None = None

    @property
    def command(self):
        """Returns the current command."""

        if not self._command:
            raise AttributeError("Command not set")

        return self._command

    @command.setter
    def command(self, value: Command[Actor_co] | None):
        """Sets the current command."""

        self._command = value

    def reset(self):
        """Resets the exposure delegate."""

        self.exposure_data = None
        self.command = None

        if self.lock.locked():
            self.lock.release()

    def fail(self, message: str = None):
        """Fail a command."""

        if message:
            self.command.fail(error=message)
        else:
            self.command.fail()

        self.reset()

        return False

    async def expose(
        self,
        command: Command[Actor_co],
        controllers: List[ArchonController],
        flavour: str = "object",
        exposure_time: float = 1.0,
        readout: bool = True,
        **readout_params,
    ):

        self.command = command

        if self.lock.locked():
            return self.fail("The expose delegate is locked.")

        if flavour == "bias":
            exposure_time = 0.0
        else:
            if exposure_time is None:
                return self.fail(f"Exposure time required for flavour {flavour!r}.")

        self.expose_data = ExposeData(
            exposure_time=exposure_time,
            flavour=flavour,
            controllers=controllers,
        )

        if not (await self.check_expose()):
            return False

        next_exp_file = self._prepare_directories()

        config = self.actor.config

        # Lock until the exposure is done.
        await self.lock.acquire()

        with open(next_exp_file, "r") as fd:
            data = fd.read().strip()
            next_exp_no: int = int(data) if data != "" else 1
            self.expose_data.exposure_no = next_exp_no

        # If the exposure is a bias or dark we don't open the shutter, but
        # otherwise we add an extra timeout to allow for the code that handles
        # the shutter to open and close it and control the exposure time that way.
        if exposure_time == 0.0 or flavour in ["bias", "dark"]:
            etime = 0.0
        else:
            etime = exposure_time + config["timeouts"]["expose_timeout"]

        jobs = [
            asyncio.create_task(controller.expose(etime, readout=False))
            for controller in controllers
        ]

        try:
            c_list = ", ".join([controller.name for controller in controllers])
            self.command.debug(text=f"Starting exposure in controllers {c_list}.")
            await asyncio.gather(*jobs)
        except BaseException as err:
            self.command.error(error=str(err))
            self.command.error("One controller failed. Cancelling remaining tasks.")
            for job in jobs:
                if not job.done():
                    with suppress(asyncio.CancelledError):
                        job.cancel()
                        await job
            return self.fail()

        # Operate the shutter
        if not (await self.shutter(True)):
            return False

        with open(next_exp_file, "w") as fd:
            fd.write(str(next_exp_no + 1))

        if readout:
            await asyncio.sleep(exposure_time)
            return await self.readout(self.command, **readout_params)

        return True

    async def check_expose(self) -> bool:
        """Performs a series of checks to confirm we can expose."""

        for controller in self.expose_data.controllers:
            cname = controller.name
            if controller.status & ControllerStatus.EXPOSING:
                return self.fail(f"Controller {cname} is exposing.")
            elif controller.status & ControllerStatus.READOUT_PENDING:
                return self.fail(f"Controller {cname} has a read out pending.")
            elif controller.status & ControllerStatus.ERROR:
                return self.fail(f"Controller {cname} has status ERROR.")

        return True

    def _prepare_directories(self) -> pathlib.Path:
        """Prepares directories."""

        config = self.actor.config

        now = astropy.time.Time.now()
        mjd = int(now.mjd)
        self.expose_data.mjd = mjd

        # Get data directory or create it if it doesn't exist.
        data_dir = pathlib.Path(config["files"]["data_dir"])
        if not data_dir.exists():
            data_dir.mkdir(parents=True)

        # We store the next exposure number in a file at the root of the data directory.
        next_exp_file = data_dir / "nextExposureNumber"
        if not next_exp_file.exists():
            next_exp_file.touch()

        self.next_exp_file = next_exp_file

        # Get the directory for this MJD or create it.
        mjd_dir = data_dir / str(mjd)
        if not mjd_dir.exists():
            mjd_dir.mkdir(parents=True)

        return next_exp_file

    async def shutter(self, open=False) -> bool:
        """Operate the shutter."""

        return True

    async def readout(
        self,
        command: Command[Actor_co],
        extra_header={},
        delay_readout=False,
    ):
        """Reads the exposure, fetches the buffer, and writes to disk."""

        self.command = command

        if not self.lock.locked():
            return self.fail("Expose delegator is not locked.")

        if self.expose_data is None:
            return self.fail("No exposure found.")

        # Close shutter.
        if not (await self.shutter(False)):
            return False

        controllers = self.expose_data.controllers

        self.expose_data.end_time = astropy.time.Time.now()
        self.expose_data.header = extra_header
        self.expose_data.delay_readout = delay_readout

        try:
            jobs = [
                c.abort(readout=False)
                for c in controllers
                if c.status & ControllerStatus.EXPOSING
            ]
            await asyncio.gather(*jobs)
            hdus = await asyncio.gather(*[self.fetch_hdus(c) for c in controllers])
        except Exception as err:
            return self.fail(f"Failed reading out: {err}")

        c_to_hdus = {controllers[ii]: hdus[ii] for ii in range(len(controllers))}

        jobs = []
        for controller, hdus in c_to_hdus.items():
            jobs.append(self.post_process(controller, hdus))

        c_to_hdus = dict(await asyncio.gather(*jobs))

        command.debug(text="Saving HDUs.")
        await asyncio.gather(*[self.write_hdus(c, h) for c, h in c_to_hdus.items()])

        self.reset()
        return True

    async def post_process(
        self,
        controller: ArchonController,
        hdus: List[fits.PrimaryHDU],
    ):
        """Custom post-processing."""

        return

    async def build_base_header(self, controller: ArchonController, ccd_name: str):
        """Returns the basic header of the FITS file."""

        assert self.command.actor

        expose_data = self.expose_data
        assert expose_data.end_time

        header = fits.Header()

        # Basic header
        header["SPEC"] = controller.name
        header["OBSERVAT"] = self.command.actor.observatory
        header["OBSTIME"] = (expose_data.start_time.isot, "Start of the observation")
        header["EXPTIME"] = expose_data.exposure_time
        header["IMAGETYP"] = expose_data.flavour
        header["INTSTART"] = (expose_data.start_time.isot, "Start of the integration")
        header["INTEND"] = (expose_data.end_time.isot, "End of the integration")

        header["CCD"] = ccd_name

        actor = self.actor
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
                            self.command.warning(
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
                        self.command.warning(
                            text=f"Invalid keyword format for {kname}."
                        )
                        header[kname] = "N/A"
                        continue
                    kpath = kpath.format(sensor=sensor).lower()
                    value = dict_get(model, kpath)
                    if not value:
                        self.command.warning(
                            text=f"Cannot find header value {kpath} for {kname}. "
                            f"Issuing command {hcommand!r}"
                        )
                        cmd = await actor.send_command(actor.name, hcommand)
                        await cmd
                        value = dict_get(model, kpath)
                        if not value:
                            self.command.warning(text=f"Cannot retrieve {kpath}.")
                            value = "N/A"
                    header[kname] = (value, comment)

        # Convert JSON lists to tuples or astropy fails.
        for key in expose_data.header:
            if isinstance(expose_data.header[key], list):
                expose_data.header[key] = tuple(expose_data.header[key])

        header.update(expose_data.header)

        return header

    def _get_ccd_data(
        self,
        data: numpy.ndarray,
        ccd_name: str,
        ccd_info: Dict[str, Any],
    ) -> numpy.ndarray:
        """Retrieves the CCD data from the buffer frame."""

        # Because the archon can order the output taplines in different ways in the
        # frame, we allow to define the CCD area as a list of ranges and then we
        # provide options to reorder them.

        areas = ccd_info["areas"]
        ccd_parts = []
        for area in areas:
            ccd_parts.append(data[area[1] : area[3], area[0] : area[2]])

        # Concatenate the different areas.
        if len(areas) > 1:
            ccd_data = numpy.concatenate(
                ccd_parts,
                axis=ccd_info.get("concatenate_axis", 0),
            )
        else:
            ccd_data = ccd_parts[0]

        if ccd_info.get("framemode", None):
            if ccd_info["framemode"] == "top":
                # This is useful if FRAMEMODE="TOP" (first read rows are always the
                # first rows in the buffer array).
                splits = numpy.split(ccd_data, 2, axis=1)
                splits[0] = splits[0][::-1, :]
                splits[1] = splits[1][:, ::-1]
                ccd_data = numpy.vstack(splits[::-1])

        return ccd_data

    async def fetch_hdus(self, controller: ArchonController) -> List[fits.PrimaryHDU]:
        """Waits for readout to complete, fetches the buffer, and creates the HDUs."""

        config = self.actor.config
        expose_data = self.expose_data

        # Read device
        self.command.debug(text=f"Reading out {controller.name}.")
        await controller.readout(delay=expose_data.delay_readout)

        # Fetch buffer
        self.command.debug(text=f"Fetching {controller.name} buffer.")
        data = await controller.fetch()

        ccd_info = config["controllers"][controller.name]["detectors"]
        hdus = []
        for ccd_name in ccd_info:
            header = await self.build_base_header(controller, ccd_name)
            ccd_data = self._get_ccd_data(data, ccd_name, ccd_info[ccd_name])
            hdus.append(fits.PrimaryHDU(data=ccd_data, header=header))

        return hdus

    async def write_hdus(
        self,
        controller: ArchonController,
        hdus: List[fits.PrimaryHDU],
    ):
        """Writes HDUs to disk."""

        loop = asyncio.get_running_loop()

        expose_data = self.expose_data
        config = self.actor.config

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
                # Astropy compresses with gzip -9 which takes forever.
                # Instead we compress manually with -1, which is still pretty good.
                await loop.run_in_executor(None, hdu.writeto, file_path[:-3])
                await gzip_async(file_path[:-3], complevel=1)
            else:
                await loop.run_in_executor(None, hdu.writeto, file_path)

            assert os.path.exists(file_path), "Failed writing image to disk."

            basename = os.path.basename(file_path)
            self.command.info(text=f"File {basename} written to disk.")
            self.command.debug(filename=file_path)

        return


@dataclass
class ExposeData:
    """Data about the ongoing exposure."""

    exposure_time: float
    flavour: str
    controllers: list[ArchonController]
    start_time: astropy.time.Time = astropy.time.Time.now()
    end_time: astropy.time.Time | None = None
    mjd: int = 0
    exposure_no: int = 0
    header: Dict[str, Any] = field(default_factory=dict)
    delay_readout: int = 0


def dict_get(d, k: str | list):
    """Recursive dictionary get."""

    if isinstance(k, str):
        k = k.split(".")

    if d[k[0]].value is None:
        return {}

    return reduce(lambda c, k: c.get(k, {}), k[1:], d[k[0]].value)
