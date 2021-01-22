#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import functools

from typing import Optional

import click
from clu.command import BaseCommand, Command

from archon.controller.controller import ArchonController

__all__ = ["parallel_controllers", "error_controller", "check_controller"]


controller_list = click.option(
    "-c",
    "--controller",
    "controller_list",
    type=str,
    help="Controllers to which to talk.",
)


def parallel_controllers():
    """A decarator that executes the same command for multiple controllers.

    When decorated with `.parallel_controllers`, the command gets an additional option
    ``controllers`` which allows to pass a list of controllers. If not controllers are
    passed, all the available controllers are used.

    The callback is called for each one of the selected controllers as the second
    argument (after the command itself). All the controller callbacks are executed
    concurrently as tasks. If one of the tasks raises an exception, all the other tasks
    are immediately cancelled and the command is failed.

    And example of use is ::

        @parser.command()
        @click.argument("archon_command", metavar="COMMAND", type=str)
        @parallel_controllers()
        async def talk(command, controller, archon_command):
            ...

    where ``controller`` receives an instance of `.ArchonController`. Within the
    callback you should not fail or finish the command; instead use
    :meth:`~clu.command.BaseCommand.error` or :meth:`~clu.command.BaseCommand.warning`.
    Your replies to the users must indicate to what controller they refer. If you want
    to force all the concurrent tasks to fail, raise an exception.
    """

    def decorator(f):
        @functools.wraps(f)
        @controller_list
        async def wrapper(
            command: BaseCommand,
            controllers: dict[str, ArchonController],
            controller_list: Optional[str] = None,
            **kwargs,
        ):
            if controller_list:
                controller_keys = map(lambda x: x.strip(), controller_list.split(","))
            else:
                controller_keys = controllers.keys()

            if len(list(controller_keys)) == 0:
                return command.fail("No controllers are available.")

            tasks: list[asyncio.Task] = []
            for k in controller_keys:
                if k not in controllers:
                    return command.fail(f"Invalid controller {k!r}.")
                if not controllers[k].is_connected():
                    return command.fail(f"Controller {k!r} is not connected.")
                tasks.append(asyncio.create_task(f(command, controllers[k], **kwargs)))

            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_EXCEPTION
            )

            if len(pending) > 0:
                for p in pending:
                    p.cancel()
                return command.fail("Some tasks raised exceptions.")

            return command.finish()

        return functools.update_wrapper(wrapper, f)

    return decorator


def error_controller(command: Command, controller: ArchonController, message: str):
    """Issues a ``error_controller`` message."""
    command.error(
        controller_error={
            "controller": controller.name,
            "error": message,
        }
    )


def check_controller(command: Command, controller: ArchonController) -> bool:
    """Performs sanity check in the controller.

    Outputs error messages if a problem is found. Return `False` if the controller
    is not in a valid state.
    """
    if not controller.is_connected():
        error_controller(command, controller, "Controller not connected.")
        return False

    return True
