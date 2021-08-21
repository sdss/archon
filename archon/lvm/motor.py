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

from archon.exceptions import ArchonError

from . import config


if TYPE_CHECKING:
    from clu.command import Command
    from drift import Drift


async def is_device_powered(device: str, drift: Drift) -> bool:
    """Checks if a devices is powered and available."""

    dev = drift.get_device(device)

    if (await dev.read())[0] == "open":
        return False

    return True


async def get_motor_status(
    controller: str,
    motors: str | List[str],
    drift: Optional[Drift] = None,
) -> Dict[str, Dict[str, str]]:
    """Returns the status of the queried motors.

    Parameters
    ----------
    controller
        The controller for which we are asking the status of the motors.
    motors
        The motor name or a list of motor names. If the latter, the motors will be
        queried concurrently.
    drift
        An instance of ``Drift`` to be used to check if the devices are connected.
        Must correspond to the WAGO of the controller IEB.

    Returns
    -------
    dict
        A dictionary of motor name to status.

    """

    # Make recursive.
    if not isinstance(motors, str):
        data = await asyncio.gather(
            *[get_motor_status(controller, m, drift=drift) for m in motors]
        )
        final_dict = {}
        for d in data:
            final_dict.update(d)
        return final_dict

    result = {motors: {"status": "?", "bits": "?"}}

    # The rest assumes a single motor.
    if drift:
        if not (await is_device_powered(motors, drift)):
            return result

    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection(
                config["devices"]["motor_controllers"][controller][motors]["host"],
                config["devices"]["motor_controllers"][controller][motors]["port"],
            ),
            5,
        )
    except (asyncio.TimeoutError, OSError):
        return result

    w.write(b"\00\07IS\r")
    await w.drain()

    try:
        reply = await asyncio.wait_for(r.readuntil(b"\r"), 1)
    except asyncio.TimeoutError:
        return result
    finally:
        w.close()
        await w.wait_closed()

    match = re.search(b"\x00\x07IS=([0-1]{8})\r$", reply)
    if match is None:
        return result

    bits = match.group(1).decode()
    result[motors]["bits"] = bits

    status = parse_IS(reply, motors)

    if not status:
        return result

    result[motors]["status"] = status
    return result


def parse_IS(reply: bytes, device: str):
    """Parses the reply to the shutter IS command."""

    match = re.search(b"\x00\x07IS=([0-1])([0-1])[0-1]{6}\r$", reply)
    if match is None:
        return False

    if match.groups() == (b"1", b"0"):
        if device in ["shutter", "hartmann_right"]:
            return "open"
        else:
            return "closed"
    elif match.groups() == (b"0", b"1"):
        if device in ["shutter", "hartmann_right"]:
            return "closed"
        else:
            return "open"
    else:
        return False


async def move_motor(
    controller: str,
    motor: str,
    action: str,
    drift: Optional[Drift] = None,
) -> bool:
    """Moves a motor."""

    if drift and not (await is_device_powered(motor, drift)):
        raise ArchonError(f"{motor} is not powered.")

    assert action in ["open", "close", "init", "home"]

    current = (await get_motor_status(controller, motor))[motor]["status"]
    if (current == "closed" and action == "close") or current == action:
        return True

    r, w = await asyncio.wait_for(
        asyncio.open_connection(
            config["devices"]["motor_controllers"][controller][motor]["host"],
            config["devices"]["motor_controllers"][controller][motor]["port"],
        ),
        5,
    )

    if action == "open":
        sequence = "QX3"
    elif action == "close":
        sequence = "QX4"
    elif action == "init":
        sequence = "QX1"
    elif action == "home":
        sequence = "QX2"
    else:
        raise ValueError(f"Invalid action {action!r}.")

    w.write(b"\00\07" + sequence.encode() + b"\r")
    await w.drain()

    while True:
        try:
            reply = await asyncio.wait_for(r.readuntil(b"\r"), 3)
            if b"ERR" in reply:
                return False
            elif b"DONE" in reply:
                return True
        finally:
            w.close()
            await w.wait_closed()


async def report_motors(
    command: Command,
    controller: str,
    motors=["shutter", "hartmann_left", "hartmann_right"],
    drift=None,
    write=True,
) -> Dict[str, Dict]:
    """Reports status of the motors to actor users."""

    motors_dict = {}

    for dev in motors:
        try:
            powered = await is_device_powered(dev, drift)
        except Exception as err:
            command.warning(error=f"Failed checking {dev!r} power status: {err}")
            continue

        if not powered:
            motors_dict[dev] = {
                controller: {
                    "power": False,
                    "status": "?",
                    "bits": "?",
                }
            }
        else:
            motors_dict[dev] = {
                controller: {
                    "power": True,
                    "status": "?",
                    "bits": "?",
                }
            }

    for dev in motors_dict:
        if motors_dict[dev][controller]["power"] is True:
            try:

                dev_status = (await get_motor_status(controller, dev))[dev]
            except Exception as err:
                command.warning(error=f"Failed getting status of device {dev!r}: {err}")
                continue
        else:
            continue

        if dev_status is not None:
            motors_dict[dev][controller].update(dev_status)

    if write:
        command.info(**motors_dict)

    return motors_dict
