#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-10-26
# @Filename: __main__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import os
import signal
from contextlib import suppress

from typing import Dict, Type

import click
from click_default_group import DefaultGroup
from clu.tools import cli_coro

from sdsstools.daemonizer import DaemonGroup

import archon as archonmod
from archon.actor import ArchonActor
from archon.lvm import LVMActor
from archon.tools import get_profile_name


ACTOR_PROFILE: Dict[str, Type[ArchonActor]] = {"lvm": LVMActor}


async def shutdown(signal, loop, actor):
    """Cancel tasks, including run_forever()."""

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]

    with suppress(asyncio.CancelledError):
        await asyncio.gather(*tasks)


@click.group(cls=DefaultGroup, default="actor", default_if_no_args=True)
@click.option(
    "-p",
    "--profile",
    type=click.Choice(["boss", "lvm"], case_sensitive=False),
    help="The profile to use. If not provided, infered from the domain name.",
)
@click.option(
    "-c",
    "--config",
    "config_file",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the user configuration file.",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Debug mode. Use additional v for more details.",
)
@click.pass_context
def archon(ctx, profile, config_file, verbose):
    """Archon controller"""

    # Update internal config
    if config_file:
        archonmod.config.load(config_file)

    ctx.obj = {"verbose": verbose, "config_file": config_file, "profile": profile}


@archon.group(cls=DaemonGroup, prog="archon_actor", workdir=os.getcwd(), umask=0o002)
@click.pass_context
@cli_coro
async def actor(ctx):
    """Runs the actor."""

    config_file = ctx.obj["config_file"]

    profile = ctx.obj["profile"]
    if profile is None:
        profile = get_profile_name()

    profile = profile.lower()
    if profile not in ACTOR_PROFILE:
        raise ValueError(f"Invalid profile {profile!r}.")

    Actor = ACTOR_PROFILE[profile]

    archon_actor = Actor.from_config(config_file)

    if ctx.obj["verbose"]:
        archon_actor.log.fh.setLevel(0)
        archon_actor.log.sh.setLevel(0)

    loop = asyncio.get_event_loop()

    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s,
            lambda s=s: asyncio.create_task(shutdown(s, loop, archon_actor)),
        )

    try:
        await archon_actor.start()
        await archon_actor.run_forever()  # type: ignore
    except asyncio.CancelledError:
        pass
    finally:
        await archon_actor.stop()
        loop.stop()


if __name__ == "__main__":
    archon()
