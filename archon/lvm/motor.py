#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-30
# @Filename: motor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import re

from typing import TYPE_CHECKING, Dict, List, Optional

from . import config


if TYPE_CHECKING:
    from drift import Drift


async def is_device_powered(device: str, drift: Drift) -> bool:
    """Checks if a devices is powered and available."""

    dev = drift.get_device(device)

    if (await dev.read())[0] == "open":
        return False

    return True


async def get_motor_status(
    motors: str | List[str], drift: Optional[Drift] = None
) -> Dict[str, bool | None]:
    """Returns the status of the queried motors.

    Parameters
    ----------
    motors
        The motor name or a list of motor names. If the latter, the motors will be
        queried concurrently.
    drift
        An instance of ``Drift`` to be used to check if the devices are connected.

    Returns
    -------
    dict
        A dictionary of motor name to status. `True` means open, while `False`
        is closed. If the device is not powered or otherwise in a bad state, returns
        `None`.

    """

    if not isinstance(motors, str):
        data = await asyncio.gather(*[get_motor_status(m, drift) for m in motors])
        final_dict = {}
        for d in data:
            final_dict.update(d)
        return final_dict

    if drift:
        if not (await is_device_powered(motors, drift)):
            return {motors: None}

    r, w = await asyncio.open_connection(
        config["devices"]["motor_controllers"][motors]["host"],
        config["devices"]["motor_controllers"][motors]["port"],
    )

    w.write(b"\00\07IS\r")
    await w.drain()

    reply = await r.readuntil(b"\r")
    status = parse_IS(reply)

    if status is False:
        return {motors: None}
    else:
        return {motors: False if status == "closed" else True}


def parse_IS(reply: bytes):
    """Parses the reply to the shutter IS command."""

    match = re.search(b"\x00\x07IS=([0-1])([0-1])[0-1]{6}\r$", reply)
    if match is None:
        return False

    if match.groups() == (b"1", b"0"):
        return "open"
    elif match.groups() == (b"0", b"1"):
        return "closed"
    else:
        return False
