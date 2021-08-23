#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-29
# @Filename: delegate.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING, List, Tuple

from astropy.io import fits

from archon.actor import ExposureDelegate
from archon.controller.controller import ArchonController

from .motor import get_motor_status, is_device_powered, move_motor
from .tools import read_govee, read_pressure


if TYPE_CHECKING:
    from .actor import LVMActor  # noqa


class LVMExposeDelegate(ExposureDelegate["LVMActor"]):
    """Expose delegate for LVM."""

    def __init__(self, actor):

        super().__init__(actor)

        self.use_shutter = False

    def reset(self):
        self.use_shutter = False
        return super().reset()

    async def check_expose(self) -> bool:
        """Performs a series of checks to confirm we can expose."""

        base_checks = await super().check_expose()
        if not base_checks:
            return False

        if self.use_shutter:
            controllers = self.expose_data.controllers
            jobs_power = []
            jobs_status = []
            for controller in controllers:
                drift = self.actor.drift[controller.name]
                jobs_power.append(is_device_powered("shutter", drift))
                jobs_status.append(get_motor_status(controller.name, "shutter", drift))

            results = await asyncio.gather(*jobs_power)
            if not all(results):
                self.fail("Some shutters are not powered.")
                return False

            results = await asyncio.gather(*jobs_status)
            for result in results:
                if result["shutter"]["status"] != "closed":
                    return self.fail("Some shutters are not closed.")

        return True

    async def shutter(self, open, retry=False):
        """Operate the shutter."""

        if not self.use_shutter:
            return True

        expose_data = self.expose_data

        if expose_data.exposure_time == 0 or expose_data.flavour in ["bias", "dark"]:
            return True

        action = "open" if open else "close"

        self.command.debug(text=f"Moving shutters to {action}.")

        jobs = []
        for controller in self.expose_data.controllers:
            jobs.append(move_motor(controller.name, "shutter", action))
        results = await asyncio.gather(*jobs, return_exceptions=True)

        if not all(results):
            if action == "close" and retry is False:
                self.command.warning(text="Some shutters failed to close. Retrying.")
                return await self.shutter(False, retry=True)
            else:
                return self.fail("Some shutters failed to move.")

        if retry is True:
            return self.fail("Closed all shutters but failing now.")

        return True

    async def post_process(
        self,
        controller: ArchonController,
        hdus: List[fits.PrimaryHDU],
    ) -> Tuple[ArchonController, List[fits.PrimaryHDU]]:
        """Post-process images."""

        self.command.debug(text="Running exposure post-process.")

        # Govee lab temperature and RH.
        try:
            temp, hum = await read_govee()
        except BaseException as err:
            self.command.warning(text=f"Failed retriving H5179 data: {err}")
            temp = -999.0
            hum = -999.0

        for hdu in hdus:
            hdu.header["LABTEMP"] = (temp, "Govee H5179 lab temperature [C]")
            hdu.header["LABHUMID"] = (hum, "Govee H5179 lab humidity [%]")

        # Record hartmann status
        try:
            hartmann = await get_motor_status(
                controller.name,
                ["hartmann_left", "hartmann_right"],
                drift=self.actor.drift[controller.name],
            )
        except Exception as err:
            self.command.warning(text=f"Failed retrieving hartmann door status: {err}")
            hartmann = {
                "hartmann_left": {"status": "?"},
                "hartmann_right": {"status": "?"},
            }

        for hdu in hdus:
            for door in ["left", "right"]:
                if hartmann[f"hartmann_{door}"]["status"] == "open":
                    hartmann[f"hartmann_{door}"]["status"] = "0"
                elif hartmann[f"hartmann_{door}"]["status"] == "closed":
                    hartmann[f"hartmann_{door}"]["status"] = "1"
            left = hartmann["hartmann_left"]["status"]
            right = hartmann["hartmann_right"]["status"]
            hdu.header["HARTMANN"] = (f"{left} {right}", "Left/right. 0=open 1=closed")

        # Record lamp status.
        for lamp_name, lamp_config in self.actor.lamps.items():
            try:
                value = await self.actor.dli.get_outlet_state(**lamp_config)
                value = "ON" if value is True else "OFF"
            except Exception as err:
                self.command.warning(
                    text=f"Failed retrieving status of lamp {lamp_name}: {err}"
                )
                value = "?"
            for hdu in hdus:
                hdu.header[lamp_name.upper()] = (value, f"Status of lamp {lamp_name}")

        # Record pressure
        for hdu in hdus:
            ccd = hdu.header["CCD"]
            value = -999.0
            if "pressure" in self.actor.config["devices"]:
                if ccd in self.actor.config["devices"]["pressure"]:
                    data = self.actor.config["devices"]["pressure"][ccd]
                    pressure = await read_pressure(**data)
                    if value is not None:
                        value = pressure
            hdu.header["PRESSURE"] = (value, "Cryostat pressure [torr]")

        return (controller, hdus)
