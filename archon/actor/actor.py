#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import os

from clu.actor import AMQPActor

from archon import __version__
from archon.controller.command import ArchonCommand
from archon.controller.controller import ArchonController

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

        self.version = __version__

    async def start(self):
        """Start the actor and connect the controllers."""
        for controller in self.controllers.values():
            await controller.start()
        await super().start()

        self._fetch_log_jobs = [
            asyncio.create_task(self._fetch_log(controller))
            for controller in self.controllers.values()
        ]

    @classmethod
    def from_config(cls, config, *args, **kwargs):
        """Creates an actor from a configuration file."""
        instance = super(ArchonActor, cls).from_config(config, *args, **kwargs)
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
                    await self.write(
                        controller_log=dict(
                            controller=controller.name,
                            log=str(cmd.replies[0].reply),
                        )
                    )
                    continue  # There may be more messages, so don't wait.
            await asyncio.sleep(1)
