#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-30
# @Filename: commands.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

from typing import Any

import click
from drift import Drift, Relay

from archon.controller.controller import ArchonController

from ..actor.commands import parser
from ..actor.tools import check_controller, controller_list, parallel_controllers
from .motor import get_motor_status, is_device_powered, move_motor, report_motors
from .tools import read_pressure
from .wago import read_many


@parser.group()
def lvm():
    """Commands specific to LVM."""
    pass


@lvm.command()
@parallel_controllers(check=False)
async def status(command, controller):
    """Reports the status of the LVM devices."""

    config = command.actor.config
    drift: Drift = command.actor.drift[controller.name]

    SENSORS = []
    for module in drift.modules.values():
        for device in module.devices.values():
            if device.category in ["temperature", "humidity"]:
                SENSORS.append(device.name.lower())

    # Run most tasks concurrently.
    tasks = [
        report_motors(command, controller.name, drift=drift, write=False),
        read_many(command, SENSORS, drift),
        command.actor.dli.report_lamps(command, write=False),
    ]
    data: Any = await asyncio.gather(*tasks)

    lvm_status = {}

    # Status of motor controllers
    motors_dict = data[0]
    lvm_status.update(**motors_dict)

    # Temperatures and RH
    sensor_data = data[1]
    environmental = {}
    for sensor in SENSORS:
        environmental[sensor] = round(sensor_data.get(sensor, -999.0), 2)

    lvm_status["environmental"] = {controller.name: environmental}

    # Lamps
    lvm_status["lamps"] = data[2]

    # Pressure.
    pressure_tasks = []
    if "pressure" in config["devices"]:
        for _, data in config["devices"]["pressure"].items():
            pressure_tasks.append(read_pressure(**data))
        presure_results = await asyncio.gather(*pressure_tasks)

        pressure = {}
        for ii, ccd in enumerate(config["devices"]["pressure"]):
            value = presure_results[ii]
            if value is False:
                value = -999.0
            pressure[ccd] = value
        lvm_status["pressure"] = pressure

    lvm_status = {key: value for key, value in lvm_status.items() if value != {}}

    command.info(**lvm_status)

    return True


@lvm.command()
@click.argument("CONTROLLER", type=str, nargs=1)
@click.option("--open", "action", flag_value="open", help="Open shutter.")
@click.option("--close", "action", flag_value="close", help="Close shutter.")
@click.option("--home", "action", flag_value="home", help="Home shutter.")
@click.option("--init", "action", flag_value="init", help="Init shutter.")
async def shutter(command, controllers, controller, action):
    """Commands the shutter. Without flags, reports the status of the shutter."""

    if controller not in command.actor.drift:
        return command.fail(error=f"Unknown controller {controller}.")

    drift: Drift = command.actor.drift[controller]

    shutter = (
        await report_motors(
            command,
            controller,
            motors=["shutter"],
            drift=drift,
            write=False,
        )
    )["shutter"]

    if action is None:
        return command.finish(shutter=shutter)
    else:
        if shutter[controller]["power"] is not True:
            command.info(shutter=shutter)
            return command.fail(
                error=f"Cannot command {controller} shutter because it is not powered. "
                "Use the 'lvm power' command to turn the power on."
            )

        try:
            moved = await move_motor(controller, "shutter", action)
        except asyncio.TimeoutError:
            return command.fail(error=f"Timed out trying to move {controller} shutter.")
        except Exception as err:
            return command.fail(error=f"Failed moving {controller} shutter: {err}")

        if not moved:
            return command.fail(error=f"Failed moving {controller} shutter.")
        else:
            await report_motors(command, controller, motors=["shutter"], drift=drift)
            return command.finish()


@lvm.command()
@click.argument("CONTROLLER", type=str, nargs=1)
@click.argument(
    "DOOR",
    type=click.Choice(["left", "right", "both"]),
    default="both",
    required=False,
)
@click.option("--open", "action", flag_value="open", help="Open hartmann door.")
@click.option("--close", "action", flag_value="close", help="Close hartmann door.")
@click.option("--home", "action", flag_value="home", help="Home hartmann door.")
@click.option("--init", "action", flag_value="init", help="Init hartmann door.")
async def hartmann(command, controllers, door, controller, action):
    """Commands the hartmann doors. Without flags, reports the status."""

    if controller not in command.actor.drift:
        return command.fail(error=f"Unknown controller {controller}.")

    drift: Drift = command.actor.drift[controller]

    if door == "both":
        doors = ["left", "right"]
    else:
        doors = [door]

    status = await report_motors(
        command,
        controller,
        motors=[f"hartmann_{door}" for door in doors],
        drift=drift,
        write=False,
    )

    if not action:
        return command.finish(**status)
    elif action:
        if door == "both":
            command.info(**status)
            return command.fail(error="Move one door at a time.")

        if not status["hartmann_" + door][controller]["power"]:
            command.info(**status)
            return command.fail(error="The door is not powered on.")

        key = "hartmann_" + door

        try:
            moved = await move_motor(controller, key, action)
        except asyncio.TimeoutError:
            return command.fail(error=f"Timed out trying to move {controller} {door}.")
        except Exception as err:
            return command.fail(error=f"Failed moving {controller} {door}: {err}")

        if moved is False:
            return command.fail(error=f"Failed moving {controller} {door} door.")

        await report_motors(command, controller, motors=[key], drift=drift)
        return command.finish()


@lvm.command()
@click.argument("CONTROLLER", type=str, nargs=1)
@click.argument(
    "DEVICE",
    type=click.Choice(["shutter", "hartmann_left", "hartmann_right"]),
)
@click.option(
    "--on",
    "action",
    flag_value="on",
    required=True,
    help="Turn on device",
)
@click.option(
    "--off",
    "action",
    flag_value="off",
    required=True,
    help="Turn off device",
)
async def power(command, controllers, controller, device, action):
    """Powers devices on/off. Without flags, reports the status."""

    if controller not in command.actor.drift:
        return command.fail(error=f"Unknown controller {controller}.")

    drift: Drift = command.actor.drift[controller]

    status = {"power": None, "status": "?", "bits": "?"}

    current = await is_device_powered(device, drift)

    if (current is True and action == "on") or (current is False and action == "off"):
        status["power"] = current
        command.warning(text="Device already at desired power state.")
        return command.finish()

    dev = drift.get_device(device)
    assert isinstance(dev, Relay)

    if action == "on":
        await dev.close()
        status["power"] = True
        await asyncio.sleep(5)
        try:
            result = await get_motor_status(controller, device)
            status["status"] = result[device]["status"]
            status["bits"] = result[device]["bits"]
        except Exception:
            pass
    else:
        await dev.open()
        status["power"] = False

    return command.finish(message={controller: {device: status}})


@lvm.command()
@click.argument("LAMP", type=str, nargs=1, required=False)
@click.option("--on", "state", flag_value=True, default=None, help="Turn on lamp.")
@click.option("--off", "state", flag_value=False, default=None, help="Turn off lamp.")
@click.option("--list", "-l", "list_", is_flag=True, help="Lists lamps.")
async def lamps(command, controllers, lamp, state, list_):
    """Powers lamps on/off. Without flags, reports the status."""

    lamps = command.actor.lamps
    dli = command.actor.dli

    if list_ is True:
        lamp_names = ", ".join(list(lamps.keys()))
        return command.finish(text=f"Available lamps: {lamp_names}.")

    if lamp is None:
        raise click.MissingParameter("Missing argument 'LAMP'.")

    if lamp not in lamps:
        return command.fail("Lamp not found.")

    if state is not None:
        try:
            await dli.set_outlet_state(
                lamps[lamp]["host"],
                lamps[lamp]["outlet"],
                state,
            )
        except RuntimeError as err:
            return command.fail(error=f"Failed setting lamp power: {err}")

    await dli.report_lamps(command, lamp_names=[lamp])

    return command.finish()


@lvm.command()
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
    "-c",
    "--count",
    type=int,
    default=1,
    help="Number of exposure to take.",
)
@click.option(
    "-d",
    "--delay-readout",
    type=int,
    default=0,
    help="Slow down the readout by this many seconds.",
)
@click.option("--lamp-current", type=str)
@click.option("--test-no", type=str)
@click.option("--test-iteration", type=str)
@click.option("--purpose", type=str)
@click.option("--notes", type=str)
async def expose(
    command,
    controllers,
    exposure_time,
    controller_list,
    flavour,
    count,
    delay_readout,
    lamp_current,
    test_no,
    test_iteration,
    purpose,
    notes,
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

    for __ in range(count):

        delegate = command.actor.expose_delegate
        if delegate is None:
            return command.fail(error="Cannot find expose delegate.")

        command.actor.set_log_values(
            lamp_current=lamp_current,
            test_no=test_no,
            test_iteration=test_iteration,
            purpose=purpose,
            notes=notes,
        )

        delegate.use_shutter = True
        result = await delegate.expose(
            command,
            selected_controllers,
            flavour=flavour,
            exposure_time=exposure_time,
            readout=True,
            delay_readout=delay_readout,
        )

        if not result:
            # expose will fail the command.
            return

    return command.finish()
