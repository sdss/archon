#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-30
# @Filename: commands.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import click
from drift import Drift, Relay

from archon.controller.controller import ArchonController

from ..actor.commands import parser
from ..actor.tools import check_controller, controller_list, parallel_controllers
from .motor import get_motor_status, is_device_powered, move_motor
from .wago import read_many


@parser.group()
def lvm():
    """Commands specific to LVM."""
    pass


@lvm.command()
@parallel_controllers()
async def status(command, controller):
    """Reports the status of the LVM devices."""

    drift: Drift = command.actor.drift[controller.name]

    # Read status of motor controllers
    MOTORS = ["shutter", "hartmann_left", "hartmann_right"]

    lvm_status = {}
    for dev in MOTORS:
        if not (await is_device_powered(dev, drift)):
            lvm_status[dev] = {
                "controller": controller.name,
                "power": False,
                "status": "?",
            }
        else:
            lvm_status[dev] = {
                "controller": controller.name,
                "power": True,
                "status": "?",
            }

    conn_devs = [dev for dev in MOTORS if lvm_status[dev]["power"] is True]
    dev_status = await get_motor_status(controller.name, conn_devs)

    for dev in dev_status:
        if dev_status[dev] is not None:
            lvm_status[dev]["status"] = dev_status[dev]

    # Read temperatures and RH
    SENSORS = []
    for module in drift.modules.values():
        for device in module.devices.values():
            if device.category in ["temperature", "humidity"]:
                SENSORS.append(device.name)

    sensor_data = await read_many(SENSORS, drift)
    environmental = {"controller": controller.name}
    for ii, sensor in enumerate(SENSORS):
        environmental[sensor] = sensor_data[ii]

    lvm_status["environmental"] = environmental

    # Lamps
    lamps_dict = await command.actor.dli.get_all_lamps(command)

    if len(lamps_dict) > 0:
        lvm_status["lamps"] = lamps_dict

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
    power = (await drift.read_device("shutter"))[0]

    shutter = {
        "controller": controller,
        "power": True if power == "closed" else False,
        "status": "?",
    }

    if action is None:
        if power == "closed":
            motor_status = await get_motor_status(controller, "shutter")
            shutter["status"] = motor_status["shutter"]
        return command.finish(shutter=shutter)
    else:
        if power == "open":
            command.info(shutter=shutter)
            return command.fail(
                error="Cannot command the shutter because it is powered down. "
                "Use the 'lvm power' command to turn the power on."
            )

        if not (await move_motor(controller, "shutter", action)):
            return command.fail(error="Failed commanding the shutter.")
        else:
            motor_status = await get_motor_status(controller, "shutter")
            shutter["status"] = motor_status["shutter"]
            return command.finish(shutter=shutter)


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

    status = {}

    if door == "both":
        doors = ["left", "right"]
    else:
        doors = [door]

    for d in doors:
        key = "hartmann_" + d
        status.update({key: {"controller": controller, "power": False, "status": "?"}})
        status[key]["power"] = await is_device_powered(key, drift)

        if status[key]["power"]:
            status[key]["status"] = (await get_motor_status(controller, key))[key]

    if not action:
        return command.finish(**status)
    elif action:
        if door == "both":
            command.info(**status)
            return command.fail(error="Move one door at a time.")

        if not status["hartmann_" + door]["power"]:
            command.info(**status)
            return command.fail(error="The door is not powered on.")

        key = "hartmann_" + door

        result = await move_motor(controller, key, action)
        if result is False:
            return command.fail(error=f"Failed moving {door} hartmann door.")

        status[key]["status"] = (await get_motor_status(controller, key))[key]

        return command.finish(**status)


@lvm.command()
@click.argument("CONTROLLER", type=str, nargs=1)
@click.argument(
    "DEVICE",
    type=click.Choice(["shutter", "hartmann_left", "hartmann_right"]),
)
@click.option("--on", "state", flag_value="on", required=True, help="Turn on device")
@click.option("--off", "state", flag_value="off", required=True, help="Turn off device")
async def power(command, controllers, controller, device, state):
    """Powers devices on/off. Without flags, reports the status."""

    if controller not in command.actor.drift:
        return command.fail(error=f"Unknown controller {controller}.")

    drift: Drift = command.actor.drift[controller]

    status = {controller: controller}

    current = await is_device_powered(device, drift)

    if (current is True and state == "on") or (current is False and state == "off"):
        status["power"] = current
        command.warning(text="Device already at desired power state.")
        return command.finish(message={device: status})

    dev = drift.get_device(device)
    assert isinstance(dev, Relay)

    if state == "on":
        await dev.close()
        status["power"] = True
    else:
        await dev.open()
        status["power"] = False

    await asyncio.sleep(3)

    return command.finish(message={device: status})


@lvm.command()
@click.argument("LAMP", type=str, nargs=1, required=False)
@click.option("--on", "state", flag_value=True, help="Turn on lamp.")
@click.option("--off", "state", flag_value=False, help="Turn off lamp.")
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
        await dli.set_outlet_state(lamps[lamp]["host"], lamps[lamp]["outlet"], state)

    value = await dli.get_outlet_state(lamps[lamp]["host"], lamps[lamp]["outlet"])
    return command.finish(lamps={lamp: value})


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
async def expose(command, controllers, exposure_time, controller_list, flavour):
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

    delegate = command.actor.expose_delegate
    if delegate is None:
        return command.fail(error="Cannot find expose delegate.")

    delegate.use_shutter = True
    result = await delegate.expose(
        command,
        selected_controllers,
        flavour=flavour,
        exposure_time=exposure_time,
        readout=True,
    )

    if result:
        return command.finish()
    else:
        # expose will fail the command.
        return
