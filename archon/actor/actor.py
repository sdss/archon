#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import os
import warnings
from contextlib import suppress

from clu.actor import AMQPActor

from archon import __version__
from archon.controller.command import ArchonCommand
from archon.controller.controller import ArchonController
from archon.exceptions import ArchonUserWarning

from .commands import parser as archon_command_parser

__all__ = ["ArchonActor"]


class ArchonActor(AMQPActor):
    """Archon controller actor.

    In addition to the normal arguments and keyword parameters for
    `~clu.actor.AMQPActor`, the class accepts the following parameters.

    Parameters
    ----------
    controllers
        A mapping of controller name to `.ArchonController`.
    """

    parser = archon_command_parser

    def __init__(
        self,
        *args,
        controllers: dict[str, ArchonController] = {},
        **kwargs,
    ):
        self.controllers = controllers
        self.parser_args = [controllers]

        if "schema" not in kwargs:
            kwargs["schema"] = os.path.join(
                os.path.dirname(__file__),
                "../etc/archon.json",
            )

        super().__init__(*args, **kwargs)

        self.observatory = os.environ.get("OBSERVATORY", "LCO")
        self.version = __version__

        self._exposing: bool = False

    async def start(self):
        """Start the actor and connect the controllers."""

        connect_timeout = self.config["timeouts"]["controller_connect"]

        for controller in self.controllers.values():
            try:
                await asyncio.wait_for(controller.start(), timeout=connect_timeout)
            except asyncio.TimeoutError:
                warnings.warn(
                    f"Timeout out connecting to {controller.name!r}.",
                    ArchonUserWarning,
                )

        await super().start()

        self._fetch_log_jobs = [
            asyncio.create_task(self._fetch_log(controller))
            for controller in self.controllers.values()
        ]

        self._status_jobs = [
            asyncio.create_task(self._report_status(controller))
            for controller in self.controllers.values()
        ]

    async def stop(self):
        with suppress(asyncio.CancelledError):
            for task in self._fetch_log_jobs:
                task.cancel()
                await task
        return super().stop()

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Creates an actor from a configuration file."""
        instance = super(ArchonActor, cls).from_config(config, *args, **kwargs)
        assert isinstance(instance, ArchonActor)
        if "controllers" in instance.config:
            controllers = {
                ctrname: ArchonController(
                    ctr["host"],
                    ctr["port"],
                    name=ctrname,
                )
                for (ctrname, ctr) in instance.config["controllers"].items()
            }
            instance.controllers = controllers
            instance.parser_args = [controllers]  # Need to refresh this
        return instance

    def can_expose(self) -> bool:
        """Checks if the actor can take a new exposure."""
        # TODO: Ideally this would be a programmatic check, but I'm not sure it's
        # easy to do. One can know if the buffers are being written to, but not
        # easily know if the timing script is running.
        return self._exposing

    async def _fetch_log(self, controller: ArchonController):
        """Fetches the log and outputs new messages.

        This is not implemented as a timed command because we don't want a new command
        popping up and running every second. We write to all users only when there's
        a new log.
        """
        while True:
            cmd: ArchonCommand = await controller.send_command("FETCHLOG")
            if cmd.succeeded() and len(cmd.replies) == 1:
                if str(cmd.replies[0].reply) != "(null)":
                    self.write(
                        log=dict(
                            controller=controller.name,
                            log=str(cmd.replies[0].reply),
                        )
                    )
                    continue  # There may be more messages, so don't wait.
            await asyncio.sleep(1)

    async def _report_status(self, controller: ArchonController):
        """Reports the status of the controller."""
        async for status in controller.yield_status():
            self.write(
                status=dict(
                    controller=controller.name,
                    status=status.name,
                )
            )
