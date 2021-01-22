import abc
import asyncio
import logging
from os import PathLike

from typing import Any, Type, TypeVar

from sdsstools.logger import SDSSLogger

T = TypeVar("T")

class BaseClient(metaclass=abc.ABCMeta):
    """A base client that can be used for listening or for an actor.

    This class defines a new client. Clients differ from actors in that
    they do not receive commands or issue replies, but do send commands to
    other actors and listen to the keyword-value flow. All actors are also
    clients and any actor should subclass from `.BaseClient`.

    Normally a new instance of a client or actor is created by passing a
    configuration file path to `.from_config` which defines how the
    client must be started.

    Parameters
    ----------
    name : str
        The name of the actor.
    version : str
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir : str
        The directory where to store the file logs.
    log : ~logging.Logger
        A `~logging.Logger` instance to be used for logging instead of creating
        a new one.
    verbose : bool or int
        Whether to log to stdout. Can be an integer logging level.

    """

    name = None
    def __init__(
        self,
        name: str,
        version: str = ...,
        loop: asyncio.AbstractEventLoop | None = ...,
        log_dir: str | None = ...,
        log: logging.Logger | None = ...,
        verbose: bool = ...,
    ):
        self.config: dict[Any, Any]
        self.log: SDSSLogger
        ...
    @abc.abstractmethod
    async def start(self):
        """Runs the client."""
        ...
    async def stop(self):
        """Shuts down all the remaining tasks."""
        ...
    @staticmethod
    def _parse_config(config: dict[Any, Any]) -> dict[Any, Any]: ...
    @classmethod
    def from_config(
        cls: Type[T], config: dict[Any, Any] | PathLike, *args, **kwargs
    ) -> T:
        """Parses a configuration file.

        Parameters
        ----------
        config : dict or str
            A configuration dictionary or the path to a YAML configuration
            file. If the file contains a section called ``'actor'`` or
            ``'client'``, that section will be used instead of the whole
            file.

        """
        ...
    def setup_logger(
        self, log: logging.Logger | None, log_dir: PathLike | None, verbose: bool = ...
    ):
        """Starts the file logger."""
        ...
    def send_command(self):
        """Sends a command to an actor and returns a `.Command` instance."""
        ...

Schema = dict[Any, Any]

class BaseActor(BaseClient):
    """An actor based on `asyncio`.

    This class expands `.BaseClient` with a parsing system for new commands
    and placeholders for methods for handling new commands and writing replies,
    which should be overridden by the specific actors.

    """

    schema: Schema | None = None
    def __init__(self, *args, schema: Schema = ..., **kwargs): ...
    def validate_schema(self, schema: Schema) -> Schema:
        """Loads and validates the actor schema."""
        ...
    @abc.abstractmethod
    def new_command(self):
        """Handles a new command.

        Must be overridden by the subclass and call `.parse_command`
        with a `.Command` object.

        """
        ...
    @abc.abstractmethod
    def parse_command(self, command):
        """Parses and executes a `.Command`. Must be overridden."""
        ...
    def send_command(self):
        """Sends a command to another actor."""
        ...
    @abc.abstractmethod
    def write(self):
        """Writes a message to user(s). To be overridden by the subclasses."""
        ...
