#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-01
# @Filename: lvm_lab.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import warnings

import click
import clu
from clu.client import AMQPClient

from sdsstools import get_logger
from sdsstools.daemonizer import cli_coro

from archon.controller.maskbits import ControllerStatus as CS


warnings.simplefilter("ignore", clu.exceptions.CluWarning)

log = get_logger("archon-lvm-lab")


SHUTTER = ("10.7.45.27", 7776)
RABBITMQ = ("localhost", 5672)
SENS4 = ("10.7.45.30", 1112)


async def command_shutter(command: str) -> bool | bytes:
    """Sends a command to the shutter."""

    r, w = await asyncio.open_connection(*SHUTTER)

    w.write((f"\x00\x07{command}\r").encode())
    await w.drain()

    reply = await r.readuntil(b"\r")
    if command == "IS" and reply:
        return reply
    else:
        if reply != b"\x00\x07%\r":
            return False
        else:
            await asyncio.sleep(0.61)
            reply = await r.readuntil(b"\r")
            if b"DONE" in reply:
                return True
            else:
                return False


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


async def check_shutter():
    """Checks the status of the shutter and closes it if open."""

    log.debug("Checking shutter.")

    shutter_is = await command_shutter("IS")
    assert isinstance(shutter_is, bytes)
    shutter_status = parse_IS(shutter_is)
    if shutter_status is None:
        log.error("Shutter is in a bad state.")
        sys.exit(1)
    elif shutter_status == "open":
        log.warning("Shutter is open. Closing it.")
        result = await command_shutter("QX4")
        if result is False:
            log.error("Failed closing the shutter. Fix the problem manually.")
            sys.exit(1)


async def get_controller_status(client: clu.AMQPClient) -> CS:
    """Returns the status of the controller."""

    log.debug("Checking controller.")

    cmd = await (await client.send_command("archon", "status"))
    if cmd.status.did_fail:
        log.error("Failed getting status from the controller.")
        sys.exit(1)

    status = client.models["archon"]["status"].value["status"]
    return CS(status)


async def close_shutter_after(delay: float):
    """Waits ``delay`` before closing the shutter."""

    await asyncio.sleep(delay)

    log.debug("Closing shutter")

    result = await command_shutter("QX4")
    if result is False:
        log.error("Shutter failed to close.")
        return False

    return True


async def read_pressure():
    """Reads the pressure transducer."""

    r, w = await asyncio.open_connection(*SENS4)

    w.write(b"@253P?\\")
    await w.drain()

    reply = await r.readuntil(b"\\")
    match = re.search(r"@[0-9]{1,3}ACK([0-9.E+-]+)\\$".encode(), reply)

    if not match:
        log.warning("Failed reading pressure.")
        return "NA"

    return float(match.groups()[0])


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Output additional information.")
@click.option("-q", "--quiet", is_flag=True, help="Only output resulting image.")
def lvm_lab(verbose: bool, quiet: bool):
    """Tools for LVM lab testing."""

    if verbose:
        log.sh.setLevel(logging.DEBUG)

    if quiet:
        log.sh.setLevel(100)


@lvm_lab.command()
@click.argument("exposure-time", type=float, required=False)
@click.option(
    "-f",
    "--flavour",
    type=str,
    default="object",
    help="object, dark, or bias.",
)
@click.option(
    "-s",
    "--flush-count",
    "flush_count",
    type=int,
    default=1,
    help="Number of times to flush the detector.",
)
@click.option(
    "-d",
    "--delay-readout",
    type=int,
    default=0,
    help="Slow down the readout by this many seconds.",
)
@cli_coro()
async def expose(
    exposure_time: float,
    flavour: str,
    flush_count: int,
    delay_readout: int,
):
    """Exposes the camera, while handling the shutter and sensors."""

    if flavour != "bias" and exposure_time is None:
        raise click.UsageError("EXPOSURE-TIME is required unless --flavour=bias.")
    elif flavour == "bias":
        exposure_time = 0.0

    # Check that the actor is running.
    client = AMQPClient(
        "lvm-lab-client",
        host=RABBITMQ[0],
        port=RABBITMQ[1],
        models=["archon"],
    )
    await client.start()
    if len(client.models) == 0:
        log.error("Archon actor does not seem to be running. Run with 'archon start'")
        sys.exit(1)

    model = client.models["archon"]

    # Check that the configuration has been loaded.
    status = await get_controller_status(client)
    if status & CS.UNKNOWN:
        log.warning("Archon has not been initialised. Sending configuration file.")
        cmd = await (await client.send_command("archon", "init"))
        if cmd.status.did_fail:
            log.error("Failed initialising the Archon.")
            sys.exit(1)
        else:
            status = await get_controller_status(client)
            if not (status & CS.IDLE):
                log.error("Initialisation succeeded but the Archon is not IDLE.")
                sys.exit(1)

    # Check that the shutter responds and is closed.
    await check_shutter()

    # TODO: add option to flush before exposing.

    # If there is a readout pending, flush the camera.
    if status & CS.READOUT_PENDING:
        log.warning("Pending readout found. Aborting and flushing.")
        if status & CS.EXPOSING:
            cmd_str = "expose abort --all --flush"
        else:
            cmd_str = "flush"
        cmd = await (await client.send_command("archon", cmd_str))
        if cmd.status.did_fail:
            log.error("Failed flushing.")
            sys.exit(1)

    # Read pressure.
    log.debug("Reading pressure transducer.")
    pressure = await read_pressure()

    # Build extra header.
    header = {"PRESURE": (pressure, "Spectrograph pressure [torr]")}
    header_json = json.dumps(header, indent=None)

    # Flushing
    if flush_count > 0:
        log.info("Flushing")
        cmd = await (await client.send_command("archon", f"flush {flush_count}"))

    # Start exposure.
    log.info("Starting exposure.")
    cmd = await (
        await client.send_command(
            "archon",
            f"expose start sp1 --{flavour} {exposure_time}",
        )
    )
    if cmd.status.did_fail:
        log.error("Failed starting exposure. Trying to abort and exiting.")
        await client.send_command("archon", "expose abort --flush")
        sys.exit(1)

    if flavour != "bias" and exposure_time > 0:
        # Open shutter.
        log.debug("Opening shutter.")
        result = await command_shutter("QX3")
        if result is False:
            log.error("Shutter failed to open.")
            await command_shutter("QX4")
            await client.send_command("archon", "expose abort --flush")
            sys.exit(1)

        if not (await asyncio.create_task(close_shutter_after(exposure_time))):
            await client.send_command("archon", "expose abort --flush")
            sys.exit(1)

    # Finish exposure
    log.info("Finishing exposure and reading out.")
    if delay_readout > 0:
        log.debug(f"Readout will be delayed {delay_readout} seconds.")

    cmd = await (
        await client.send_command(
            "archon",
            f"expose finish --delay-readout {delay_readout} --header '{header_json}'",
        )
    )
    if cmd.status.did_fail:
        log.error("Failed reading out exposure.")
        sys.exit(1)

    exp_name = model["filename"].value

    if log.sh.level <= logging.INFO:
        log.info(f"Exposure saved to {exp_name}")
    else:
        print(exp_name)

    sys.exit(0)
