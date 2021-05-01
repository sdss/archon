#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-01
# @Filename: lvm_lab.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import re

import click

from sdsstools import get_logger
from sdsstools.daemonizer import cli_coro


log = get_logger("archon-lvm-lab")

SHUTTER = ("10.7.45.27", 7776)


async def command_shutter(command: str):
    """Sends a command to the shutter."""

    r, w = await asyncio.open_connection(*SHUTTER)

    w.write((f"\x00\x07{command}\r").encode())
    await w.drain()

    reply = await r.read(1024)
    return reply


def parse_IS(reply: bytes):
    """Parses the reply to the shutter IS command."""

    match = re.match(b"\x00\x07IS=([0-1])([0-1])[0-1]{6}\r", reply)
    if match is None:
        return False

    if match.groups() == (b"1", b"0"):
        return "open"
    elif match.groups() == (b"0", b"1"):
        return "close"
    else:
        return False


@click.group()
def lvm_lab():
    """Tools for LVM lab testing."""
    pass


@lvm_lab.command()
@click.option(
    "--flavour",
    "-f",
    type=str,
    default="object",
    help="object, dark, or bias.",
)
@click.argument("EXPORURE-TIME", type=float, required=False)
@cli_coro()
async def expose(exposure_time: float, flavour: str):
    """Exposes the camera, while handling the shutter and sensors."""

    shutter_is = await command_shutter("IS")
    shutter_status = parse_IS(shutter_is)
    if shutter_status is None:
        raise ValueError("Shutter is in a bad state.")
    elif shutter_status == "open":
        log.warning("Shutter is open. Closing it.")
        await command_shutter("QX3")
        await asyncio.sleep(0.5)
        shutter_status = parse_IS(await command_shutter("IS"))
        if shutter_status == [None, "open"]:
            raise ValueError("Failed closing the shutter. Fix the problem manually.")
