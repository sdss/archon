#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import fcntl
import functools
from contextlib import contextmanager
from os import PathLike

from typing import IO, Any, Generator, Tuple

import astropy.time
import click
from clu.command import BaseCommand, Command

from archon import config
from archon.controller.controller import ArchonController


__all__ = [
    "parallel_controllers",
    "error_controller",
    "check_controller",
    "open_with_lock",
    "read_govee",
]


controller_list = click.argument(
    "controller_list",
    metavar="CONTROLLERS",
    type=str,
    nargs=-1,
    required=False,
)


def parallel_controllers(check=True):
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
            controller_list: Tuple[str, ...],
            **kwargs,
        ):
            if not controller_list:
                controller_list = tuple(controllers.keys())

            if len(controller_list) == 0:
                return command.fail("No controllers are available.")

            tasks: list[asyncio.Task] = []
            for k in controller_list:
                if check:
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

            results = [task.result() for task in done]
            if False in results:
                return command.fail(error="Some controllers failed.")
            return command.finish()

        return functools.update_wrapper(wrapper, f)

    return decorator


def error_controller(command: Command, controller: ArchonController, message: str):
    """Issues a ``error_controller`` message."""

    command.error(
        text={
            "controller": controller.name,
            "text": message,
        }
    )

    return False


def check_controller(command: Command, controller: ArchonController) -> bool:
    """Performs sanity check in the controller.

    Outputs error messages if a problem is found. Return `False` if the controller
    is not in a valid state.
    """

    if not controller.is_connected():
        error_controller(command, controller, "Controller not connected.")
        return False

    return True


@contextmanager
def open_with_lock(
    filename: PathLike, mode: str = "r"
) -> Generator[IO[Any], None, None]:
    """Opens a file and adds an advisory lock on it.

    Parameters
    ----------
    filename
        The path to the file to open.
    mode
        The mode in which the file will be open.

    Raises
    ------
    BlockingIOError
        If the file is already locked.
    """

    # Open the file in read-only mode first to see if it's already locked.
    fd = open(filename, "r")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # This will cause a BlockingIOError unless not locked.
    fcntl.flock(fd, fcntl.LOCK_UN)

    # Now really open.
    with open(filename, mode) as fd:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield fd
        fcntl.flock(fd, fcntl.LOCK_UN)


async def read_govee() -> Tuple[float, float]:
    """Connects to the H5179 device and gets the lab temperature and humidity."""

    h5179 = config["sensors"]["H5179"]
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(h5179["host"], h5179["port"]),
        timeout=2,
    )
    writer.write(b"status\n")
    data = await asyncio.wait_for(reader.readline(), timeout=1)
    lines = data.decode().strip().splitlines()
    temp = hum = last = None
    for line in lines:
        name, temp, hum, __, last = line.split()
        if name == "H5179":
            break

    if temp is None or hum is None or last is None:
        raise ValueError("Did not get a measurement for H5179.")

    temp = float(temp)
    hum = float(hum)

    last_seen = astropy.time.Time(last, format="isot")
    delta = astropy.time.Time.now() - last_seen
    if delta.datetime.seconds / 60 > 10:
        raise RuntimeError("Lab metrology is over 10 minutes old.")

    return temp, hum
