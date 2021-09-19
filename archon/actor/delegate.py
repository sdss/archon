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

from typing import TYPE_CHECKING, Any, Dict, Generic, List, TypeVar, cast

import astropy.time
import numpy
from astropy.io import fits

from archon.controller.controller import ArchonController
from archon.controller.maskbits import ControllerStatus
from archon.tools import gzip_async


if TYPE_CHECKING:  # pragma: no cover
    from clu import Command

    from .actor import ArchonActor


Actor_co = TypeVar("Actor_co", bound="ArchonActor", covariant=True)


class ExposureDelegate(Generic[Actor_co]):
    """Handles the exposure workflow."""

    def __init__(self, actor: Actor_co):

        self.actor = actor

        self.expose_data: ExposeData | None = None
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

        self.expose_data = None
        self.command = None

        if self.lock.locked():
            self.lock.release()

    def fail(self, message: str = None):
        """Fails a command."""

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
        exposure_time: float | None = 1.0,
        readout: bool = True,
        binning: int = 1,
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
            binning=binning,
        )

        if not (await self.check_expose()):
            return False

        next_exp_file = self._prepare_directories()

        # Lock until the exposure is done.
        await self.lock.acquire()

        with open(next_exp_file, "r") as fd:
            data = fd.read().strip()
            next_exp_no: int = int(data) if data != "" else 1
            self.expose_data.exposure_no = next_exp_no

        # If the exposure is a bias or dark we don't open the shutter, but
        # otherwise we add an extra timeout to allow for the code that handles
        # the shutter to open and close it and control the exposure time that way.
        if exposure_time == 0.0 or flavour == "bias":
            exposure_time = 0.0

        jobs = [
            asyncio.create_task(
                controller.expose(
                    exposure_time,
                    readout=False,
                    binning=binning,
                )
            )
            for controller in controllers
        ]

        try:
            c_list = ", ".join([controller.name for controller in controllers])
            self.command.debug(text=f"Starting exposure in controllers: {c_list}.")
            await asyncio.gather(*jobs)
        except BaseException as err:
            self.command.error(error=str(err))
            self.command.error("One controller failed. Cancelling remaining tasks.")
            for job in jobs:
                if not job.done():  # pragma: no cover
                    with suppress(asyncio.CancelledError):
                        job.cancel()
                        await job
            return self.fail()

        # Operate the shutter
        if not (await self.shutter(True)):
            return self.fail("Shutter failed to open.")

        with open(next_exp_file, "w") as fd:
            fd.write(str(next_exp_no + 1))

        if readout:
            await asyncio.sleep(exposure_time)
            return await self.readout(self.command, **readout_params)

        return True

    async def check_expose(self) -> bool:
        """Performs a series of checks to confirm we can expose."""

        assert self.expose_data

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

        assert self.expose_data

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
            return self.fail("No exposure data found.")

        # Close shutter.
        if not (await self.shutter(False)):
            return self.fail("Shutter failed to close.")

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

            command.debug(text="Reading out CCDs.")
            readout_tasks = [
                controller.readout(delay=self.expose_data.delay_readout)
                for controller in controllers
            ]
            await asyncio.gather(*readout_tasks, self.readout_cotasks())

            command.debug(text="Fetching HDUs.")
            hdus = await asyncio.gather(*[self.fetch_hdus(c) for c in controllers])

        except Exception as err:
            return self.fail(f"Failed reading out: {err}")

        c_to_hdus = {controllers[ii]: hdus[ii] for ii in range(len(controllers))}

        post_process_jobs = []
        for controller, hdus in c_to_hdus.items():
            post_process_jobs.append(self.post_process(controller, hdus))

        c_to_hdus = dict(await asyncio.gather(*post_process_jobs))
        self.command.debug(text="Writing HDUs to file.")
        await asyncio.gather(*[self.write_hdus(c, h) for c, h in c_to_hdus.items()])

        self.reset()
        return True

    async def readout_cotasks(self):
        """Tasks that will be executed concurrently with readout.

        This routine can be overridden to run processes that do not need to
        wait until `.post_process`. For example, reading out sensors and
        telescope data can happen here to save time.

        """

        return

    async def fetch_hdus(self, controller: ArchonController) -> List[fits.PrimaryHDU]:
        """Waits for readout to complete, fetches the buffer, and creates the HDUs."""

        config = self.actor.config

        # Fetch buffer
        self.command.debug(text=f"Fetching {controller.name} buffer.")
        data = await controller.fetch()

        controller_info = config["controllers"][controller.name]
        hdus = []
        for ccd_name in controller_info["detectors"]:
            header = await self.build_base_header(controller, ccd_name)
            ccd_data = self._get_ccd_data(data, ccd_name, controller_info)
            hdus.append(fits.PrimaryHDU(data=ccd_data, header=header))

        return hdus

    async def write_hdus(
        self,
        controller: ArchonController,
        hdus: List[fits.PrimaryHDU],
    ):
        """Writes HDUs to disk."""

        assert self.expose_data

        expose_data = self.expose_data
        config = self.actor.config

        data_dir = pathlib.Path(config["files"]["data_dir"])
        mjd_dir = data_dir / str(expose_data.mjd)

        path: pathlib.Path = mjd_dir / config["files"]["template"]

        write_tasks = []
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

            hdu.header["filename"] = os.path.basename(file_path)
            hdu.header.insert(
                "filename",
                ("EXPNO", expose_data.exposure_no, "Exposure number"),
                after=True,
            )

            write_tasks.append(self._write_to_file(hdu, file_path))

        await asyncio.gather(*write_tasks)

        return

    async def _write_to_file(self, hdu: fits.PrimaryHDU, file_path: str):
        """Writes the HDU to file using an executor."""

        loop = asyncio.get_running_loop()

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

    async def post_process(
        self,
        controller: ArchonController,
        hdus: List[fits.PrimaryHDU],
    ):
        """Custom post-processing."""

        return (controller, hdus)

    async def build_base_header(self, controller: ArchonController, ccd_name: str):
        """Returns the basic header of the FITS file."""

        assert self.command.actor and self.expose_data

        expose_data = self.expose_data
        assert expose_data.end_time

        header = fits.Header()

        # Basic header
        header["FILENAME"] = ("", "File basename")  # Will be filled out later
        header["SPEC"] = (controller.name, "Spectrograph name")
        header["OBSERVAT"] = (self.command.actor.observatory, "Observatory")
        header["OBSTIME"] = (expose_data.start_time.isot, "Start of the observation")
        header["MJD"] = (int(expose_data.start_time.mjd), "Modified Julian Date")
        header["EXPTIME"] = (expose_data.exposure_time, "Exposure time")
        header["DARKTIME"] = (expose_data.exposure_time, "Dark time")
        header["IMAGETYP"] = (expose_data.flavour, "Image type")
        header["INTSTART"] = (expose_data.start_time.isot, "Start of the integration")
        header["INTEND"] = (expose_data.end_time.isot, "End of the integration")

        header["CCD"] = (ccd_name, "CCD name")

        config = self.actor.config
        if (
            "controllers" not in config or controller.name not in config["controllers"]
        ):  # pragma: no cover
            self.command.warning(text="Cannot retrieve controller information.")
            controller_config = {"detectors": {ccd_name: {}}, "parameters": {}}
        else:
            controller_config = config["controllers"][controller.name]
        ccd_config = controller_config["detectors"][ccd_name]

        ccdid = ccd_config.get("serial", "?")
        ccdtype = ccd_config.get("type", "?")
        gain = ccd_config.get("gain", "?")
        readnoise = ccd_config.get("readnoise", "?")

        header["CCDID"] = (ccdid, "Unique identifier of the CCD")
        header["CCDTYPE"] = (ccdtype, "CCD type")
        header["GAIN"] = (gain, "CCD gain (e-/ADU)")
        header["RDNOISE"] = (readnoise, "CCD read noise (e-)")

        binning = int(expose_data.binning)
        header["BINNING"] = (binning, "Horizontal and vertical binning")
        header["CCDSUM"] = (f"{binning} {binning}", "Horizontal and vertical binning")

        if controller_config["parameters"] == {}:  # pragma: no cover
            # This is just for extra safety, but it should never happen
            # because we need parameters to read out.
            detsize = ""
            ccdsec = ""
            biassec = ""
            trimsec = ""
            channels = ""
        else:
            parameters = controller_config["parameters"]
            pixels = parameters["pixels"]
            lines = parameters["lines"]
            overscan_lines = parameters.get("overscan_lines", 0)
            overscan_pixels = parameters.get("overscan_pixels", 0)

            channels = int(parameters["taps_per_detector"])

            p1 = pixels * channels // 2
            l1 = lines * channels // 2

            detsize = ccdsec = trimsec = f"[1:{p1}, 1:{l1}]"
            ccdsec = trimsec = detsize

            if overscan_lines == 0 and overscan_pixels == 0:
                biassec = ""
            else:
                p0 = pixels - overscan_pixels + 1
                p1 = p0 + overscan_pixels * channels // 2 - 1
                l0 = 1
                l1 = lines * channels // 2
                biassec = f"[{p0}:{p1}, {l0}:{l1}]"

        header["DETSIZE"] = (detsize, "Detector size (1-index)")
        header["CCDSEC"] = (ccdsec, "Region of CCD read (1-index)")
        header["BIASSEC"] = (biassec, "Bias section (1-index)")
        header["TRIMSEC"] = (trimsec, "Section of useful data (1-index)")

        if controller.acf_loaded:
            acf = os.path.basename(controller.acf_loaded)
        else:
            acf = "?"
        header["ARCHACF"] = (acf, "Archon ACF file loaded")

        actor = self.actor
        model = actor.model
        config = actor.config

        # Add keywords specified in the configuration file.
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
                            kpath, comment, *precision = kconfig[ccd_name]
                    elif isinstance(kconfig, list):
                        kpath, comment, *precision = kconfig
                    else:
                        self.command.warning(text=f"Invalid keyword format: {kname}.")
                        header[kname] = "N/A"
                        continue
                    kpath = kpath.lower()
                    value = dict_get(model, kpath)
                    if len(precision) > 0:
                        value = round(float(cast(float, value)), precision[0])
                    if not value:  # pragma: no cover (needs fix from CLU)
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
        controller_info: Dict[str, Any],
    ) -> numpy.ndarray:
        """Retrieves the CCD data from the buffer frame."""

        assert self.expose_data

        binning = self.expose_data.binning

        parameters = controller_info["parameters"]

        pixels = parameters["pixels"]
        lines = parameters["lines"]
        taps = parameters["taps_per_detector"]

        framemode = parameters.get("framemode", "split")
        overscan_pixels = parameters.get("overscan_pixels", 0)

        ccd_index = list(controller_info["detectors"].keys()).index(ccd_name)

        if framemode == "top":
            x0_base = ccd_index * (pixels + overscan_pixels) * taps
            x0 = x0_base

            ccd_taps = []
            for tap in range(taps):
                y0 = 0
                y1 = lines // binning

                x1 = x0 + (pixels + overscan_pixels) // binning

                ccd_taps.append(data[y0:y1, x0:x1])

                x0 = x1

            if len(ccd_taps) == 1:
                return ccd_taps[0]

            bottom = numpy.hstack(ccd_taps[0 : len(ccd_taps) // 2])
            top = numpy.hstack(ccd_taps[len(ccd_taps) // 2 :])
            ccd_data = numpy.vstack([top[:, ::-1], bottom[::-1, :]])

        elif framemode == "split":
            x0 = ccd_index * (pixels + overscan_pixels) * (taps // 2)
            x1 = x0 + (pixels + overscan_pixels) * (taps // 2)
            y0 = 0
            y1 = lines * (taps // 2)
            ccd_data = data[y0:y1, x0:x1]

        else:
            raise ValueError(f"Framemode {framemode} is supported at this time.")

        return ccd_data


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
    binning: int = 1


def dict_get(d, k: str | list):
    """Recursive dictionary get."""

    if isinstance(k, str):
        k = k.split(".")

    if d[k[0]].value is None:
        return {}

    return reduce(lambda c, k: c.get(k, {}), k[1:], d[k[0]].value)
