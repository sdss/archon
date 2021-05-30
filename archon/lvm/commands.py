#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-30
# @Filename: commands.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from typing import TYPE_CHECKING

from ..actor.commands import parser
from .motor import get_motor_status, is_device_powered
from .wago import read_many


if TYPE_CHECKING:
    from drift import Drift


@parser.group()
def lvm():
    """Commands specific to LVM."""
    pass


@lvm.command()
async def status(command, controllers):
    """Reports the status of the LVM devices."""

    drift: Drift = command.actor.drift

    # Read status of motor controllers
    MOTORS = ["shutter", "hartmann_left", "hartmann_right"]

    lvm_status = {}
    for dev in MOTORS:
        if not (await is_device_powered(dev, drift)):
            lvm_status[dev] = {"power": False, "status": "?"}
        else:
            lvm_status[dev] = {"power": True, "status": "?"}

    conn_devs = [dev for dev in MOTORS if lvm_status[dev]["power"] is True]
    dev_status = await get_motor_status(conn_devs, drift)

    for dev in dev_status:
        if dev_status[dev] is not None:
            lvm_status[dev]["status"] = "closed" if dev_status[dev] is False else "open"

    # Read temperatures and RH
    SENSORS = []
    for module in drift.modules.values():
        for device in module.devices.values():
            if device.category in ["temperature", "humidity"]:
                SENSORS.append(device.name)

    sensor_data = await read_many(SENSORS, drift)
    environmental = {}
    for ii, sensor in enumerate(SENSORS):
        environmental[sensor] = sensor_data[ii]

    lvm_status["environmental"] = environmental

    return command.finish(lvm_status=lvm_status)
