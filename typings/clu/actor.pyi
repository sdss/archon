from typing import Any

import aio_pika

from .base import BaseActor
from .client import AMQPClient
from .command import BaseCommand
from .parser import ClickParser

class AMQPActor(AMQPClient, ClickParser, BaseActor):
    def __init__(self, *args, schema: str | None = ..., **kwargs): ...
    async def start(self, **kwargs):
        """Starts the connection to the AMQP broker."""
        ...
    async def new_command(self, message: aio_pika.Message):
        """Handles a new command received by the actor."""
        ...
    async def write(
        self,
        message_code: str = ...,
        message: dict[str, Any] | None = ...,
        command: BaseCommand | None = ...,
        broadcast: bool = ...,
        no_validate: bool = ...,
        **kwargs,
    ):
        """Writes a message to user(s).

        Parameters
        ----------
        message_code : str
            The message code (e.g., ``'i'`` or ``':'``).
        message : dict
            The keywords to be output. Must be a dictionary of pairs
            ``{keyword: value}``.
        command : Command
            The command to which we are replying. If not set, it is assumed
            that this is a broadcast.
        broadcast : bool
            Whether to broadcast the message to all the users or only to the
            commander.
        no_validate : bool
            Do not validate the reply against the actor schema. This is
            ignored if the actor was not started with knowledge of its own
            schema.
        kwargs
            Keyword arguments that will be added to the message.

        """
        ...
