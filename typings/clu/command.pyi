#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2018-01-17
# @Filename: command.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import Any, Callable, Optional, TypeVar

from .base import BaseActor
from .tools import CommandStatus, StatusMixIn

T = TypeVar("T")
Message = str | dict[str, Any] | None

class BaseCommand(asyncio.Future, StatusMixIn):
    """Base class for commands of all types (user and device).

    A `BaseCommand` instance is a `~asyncio.Future` whose result gets set
    when the status is done (either successfully or not).

    Parameters
    ----------
    commander_id : str or int
        The ID of the commander issuing this command. Can be a string or an
        integer. Normally the former is used for new-style actor and the latter
        for legacy actors.
    command_id : str or int
        The ID associated to this command. As with the commander_id, it can be
        a string or an integer
    consumer_id : str or int
        The actor that is consuming this command. Normally this is our own
        actor but if we are commanding another actor ``consumer_id`` will
        be the destination actor.
    parent : .BaseCommand
        Another `.BaseCommand` object that is issuing this subcommand.
        Messages emitted by the command will use the parent ``command_id``.
    status_callback : function
        A function to call when the status changes.
    call_now : bool
        Whether to call ``status_callback`` when initialising the command.
    default_keyword : str
        The keyword to use when writing a message that does not specify a
        keyword.
    loop
        The event loop.

    """

    def __init__(
        self,
        commander_id: str | int = ...,
        command_id: str | int = ...,
        consumer_id: str | int = ...,
        parent: BaseCommand | None = ...,
        status_callback: Callable[[Any], None] = ...,
        call_now: bool = ...,
        default_keyword: str = ...,
        loop: asyncio.AbstractEventLoop | None = ...,
    ): ...
    @property
    def status(self):
        """Returns the status."""
        ...
    @status.setter
    def status(self, status: CommandStatus):
        """Sets the status. A message is output to the users.

        This setter calls `.set_status` with an empty message to the users.

        Parameters
        ----------
        status : CommandStatus or int or str
            The status to set, either as a `CommandStatus` value or the
            integer associated with the maskbit. If ``value`` is a string,
            loops over the bits in `CommandStatus` and assigns the one whose
            name matches.
        silent : bool
            Update the status but do not output it with a message to the users.

        """
        ...
    def set_status(
        self: T,
        status: CommandStatus,
        message: Message = ...,
        silent: bool = ...,
        **kwargs,
    ) -> T:
        """Same as `.status` but allows to specify a message to the users."""
        ...
    def finish(self: T, *args, **kwargs) -> T:
        """Convenience method to mark a command `~.CommandStatus.DONE`."""
        ...
    def fail(self: T, *args, **kwargs) -> T:
        """Convenience method to mark a command `~.CommandStatus.FAILED`."""
        ...
    def debug(self: T, *args, **kwargs) -> T:
        """Writes a debug-level message."""
        ...
    def info(self: T, *args, **kwargs) -> T:
        """Writes an info-level message."""
        ...
    def warning(self: T, *args, **kwargs) -> T:
        """Writes a warning-level message."""
        ...
    def error(self, *args, **kwargs):
        """Writes an error-level message (does not fail the command)."""
        ...
    def write(
        self,
        message_code: str = ...,
        message: Message = ...,
        broadcast: bool = ...,
        **kwargs,
    ):
        """Writes to the user(s).

        Parameters
        ----------
        message_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : str or dict
            The text to be output. If `None`, only the code will be written.

        """
        ...

class Command(BaseCommand):
    """A command from a user.

    Parameters
    ----------
    command_string : str
        The string that defines the body of the command.
    actor : .BaseActor
        The actor instance associated to this command.
    transport
        The TCP transport associated with this command (only relevant
        for `.LegacyActor` commands).

    """

    def __init__(
        self,
        command_string: str = ...,
        actor: BaseActor | None = ...,
        transport: Any = ...,
        **kwargs,
    ):
        self.actor: Optional[BaseActor]
        ...
    def parse(self: T) -> T:
        """Parses the command."""
        ...

class TimedCommandList(list):
    """A list of `.TimedCommand` objects that will be executed on a loop.

    Parameters
    ----------
    actor
        The actor in which the commands are to be run.
    resolution : float
        In seconds, how frequently to check if any of the `.TimedCommand` must
        be executed.

    """

    def __init__(
        self,
        actor: BaseActor,
        resolution: float = ...,
        loop: asyncio.AbstractEventLoop | None = ...,
    ): ...
    def add_command(self, command_string: str, **kwargs):
        """Adds a new `.TimedCommand`."""
        ...
    async def poller(self):
        """The polling loop."""
        ...
    def start(self: T) -> T:
        """Starts the loop."""
        ...
    async def stop(self):
        """Cancel the poller."""
        ...
    @property
    def running(self) -> bool:
        """Returns `True` if the poller is running."""
        ...

class TimedCommand(object):
    """A command to be executed on a loop.

    Parameters
    ----------
    command_string : str
        The command string to run.
    delay : float
        How many seconds to wait between repeated calls.

    """

    def __init__(self, command_string: str, delay: float = ...): ...
    async def run(self, actor: BaseActor):
        """Run the command."""
        ...
    def done(self):
        """Marks the execution of a command."""
        ...
