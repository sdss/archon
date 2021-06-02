#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-01
# @Filename: lvm_lab.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import logging
import sys
import warnings

import click
import clu
from clu.client import AMQPClient, AMQPReply

from sdsstools import get_logger
from sdsstools.daemonizer import cli_coro

from archon.controller.maskbits import ControllerStatus as CS


warnings.simplefilter("ignore", clu.exceptions.CluWarning)

log = get_logger("archon-lvm-lab")


RABBITMQ = ("localhost", 5672)
READOUT_DELAY = 45


def finish_callback(reply: AMQPReply):

    if "filename" in reply.body:
        exp_name = reply.body["filename"]
        if log.sh.level <= logging.INFO:
            log.info(f"Exposure saved to {exp_name}")
        else:
            print(exp_name)


async def get_controller_status(client: clu.AMQPClient) -> CS:
    """Returns the status of the controller."""

    log.debug("Checking controller.")

    cmd = await (await client.send_command("archon", "status"))
    if cmd.status.did_fail:
        log.error("Failed getting status from the controller.")
        sys.exit(1)

    status = client.models["archon"]["status"].value["status"]
    return CS(status)


def check_expose_task(cmd):
    """Checks the exposure task."""

    if cmd.status.did_fail:
        log.error("Exposure failed.")
        sys.exit(1)


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
    "-c",
    "--count",
    type=int,
    default=1,
    help="Number of frames to take with this configuration.",
)
@click.option(
    "-f",
    "--flavour",
    type=click.Choice(["object", "dark", "bias"]),
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
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Prompts for the log parameters.",
)
@click.option("--lamp-current", type=str)
@click.option("--test-no", type=str)
@click.option("--test-iteration", type=str)
@click.option("--purpose", type=str)
@click.option("--notes", type=str)
@cli_coro()
async def expose(
    exposure_time: float,
    count: int,
    flavour: str,
    flush_count: int,
    delay_readout: int,
    interactive: bool,
    lamp_current: str | None,
    purpose: str | None,
    notes: str | None,
    test_no: str | None,
    test_iteration: str | None,
):
    """Exposes the camera, while handling the shutter and sensors."""

    if flavour != "bias" and exposure_time is None:
        raise click.UsageError("EXPOSURE-TIME is required unless --flavour=bias.")
    elif flavour == "bias":
        exposure_time = 0.0

    # Get lab notebook values.
    if interactive:
        if test_no is None:
            test_no = input("Test #: ")
        if test_iteration is None:
            test_iteration = input("Test iteration: ")
        if lamp_current is None:
            lamp_current = input("Lamp current: ")
        if purpose is None:
            purpose = input("Purpose: ")
        if notes is None:
            notes = input("Notes: ")
    else:
        lamp_current = lamp_current or ""
        purpose = purpose or ""
        notes = notes or ""
        test_no = test_no or ""
        test_iteration = test_iteration or ""

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

    for nn in range(count):

        log.info(f"Taking exposure {nn + 1} of {count}.")

        # Flushing
        if flush_count > 0:
            log.info("Flushing")
            cmd = await (await client.send_command("archon", f"flush {flush_count}"))

        # Start exposure.
        log.info("Exposing.")
        cmd = await client.send_command(
            "archon",
            f"lvm expose --{flavour} "
            f"--delay-readout '{delay_readout}' "
            f"--lamp-current '{lamp_current}' "
            f"--purpose '{purpose}' "
            f"--notes '{notes}' "
            f"--test-no '{test_no}' "
            f"--test-iteration '{test_iteration}' "
            f"sp1 {exposure_time}",
            callback=finish_callback,
        )

        cmd.add_done_callback(check_expose_task)

        if log.sh.level <= logging.INFO:
            nsecs = int(READOUT_DELAY + exposure_time)
            with click.progressbar(range(nsecs)) as bar:
                for _ in bar:
                    await asyncio.sleep(1)

        await cmd

    sys.exit(0)
