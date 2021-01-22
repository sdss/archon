#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from clu.actor import AMQPActor

from archon import __version__
from archon.controller.controller import ArchonController

from .commands import parser as archon_command_parser

__all__ = ["ArchonActor"]


class ArchonActor(AMQPActor):
    """Archon controller actor.

    In addition to the normal arguments and keyword parameters for `~clu.actor.AMQPActor`,
    the class accepts the following parameters.

    Parameters
    ----------
    controllers
        A mapping of controller name to `.ArchonController`.
    """

    parser = archon_command_parser

    def __init__(self, *args, controllers: dict[str, ArchonController] = {}, **kwargs):
        self.controllers = controllers
        self.parser_args = [controllers]

        super().__init__(*args, **kwargs)

        self.version = __version__

    async def start(self):
        """Start the actor and connect the controllers."""
        for controller in self.controllers.values():
            await controller.start()
        await super().start()

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
