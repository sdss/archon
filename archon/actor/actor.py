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
from dataclasses import dataclass, field

from typing import Any, Dict

import astropy.time
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
        The list of `.ArchonController` instances to manage.
    """

    parser = archon_command_parser

    def __init__(
        self,
        *args,
        controllers: tuple[ArchonController, ...] = (),
        **kwargs,
    ):
        #: dict[str, ArchonController]: A mapping of controller name to controller.
        self.controllers = {c.name: c for c in controllers}

        self.parser_args = [self.controllers]

        if "schema" not in kwargs:
            kwargs["schema"] = os.path.join(
                os.path.dirname(__file__),
                "../etc/archon.json",
            )

        super().__init__(*args, **kwargs)

        self.observatory = os.environ.get("OBSERVATORY", "LCO")
        self.version = __version__

        self.expose_data: ExposeData | None = None

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
        assert isinstance(instance.config, dict)
        if "controllers" in instance.config:
            controllers = (
                ArchonController(
                    ctr["host"],
                    ctr["port"],
                    name=ctrname,
                )
                for (ctrname, ctr) in instance.config["controllers"].items()
            )
            instance.controllers = {c.name: c for c in controllers}
            instance.parser_args = [instance.controllers]  # Need to refresh this
        return instance

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
                    status=status.value,
                    status_names=[flag.name for flag in status.get_flags()],
                )
            )


@dataclass
class ExposeData:
    """Data about the ongoing exposure."""

    exposure_time: float
    flavour: str
    controllers: list[ArchonController]
    start_time: astropy.time.Time = astropy.time.Time.now()
    end_time: astropy.time.Time | None = None
    mjd: int = 0
    exposure_no: int = 0
    header: Dict[str, Any] = field(default_factory=dict)
