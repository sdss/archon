#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2020-07-30
# @Filename: client.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio
import logging

from typing import TypeVar

import aio_pika as apika

from .base import BaseClient
from .command import Command

T = TypeVar("T")

class AMQPReply(object):
    """Wrapper for an `~aio_pika.IncomingMessage` that expands and decodes it.

    Parameters
    ----------
    message : aio_pika.IncomingMessage
        The message that contains the reply.
    log : logging.Logger
        A message logger.

    Attributes
    ----------
    is_valid : bool
        Whether the message is valid and correctly parsed.
    body : dict
        The body of the message, as a JSON dictionary.
    info : dict
        The info dictionary.
    headers : dict
        The headers of the message, decoded if they are bytes.
    message_code : str
        The message code.
    sender : str
        The name of the actor that sends the reply.
    command_id
        The command ID.

    """

    def __init__(self, message: apika.IncomingMessage, log: logging.Logger | None): ...

class AMQPClient(BaseClient):
    """Defines a new client based on the AMQP standard.

    To start a new client first instantiate the class and then run `.start` as
    a coroutine. Note that `.start` does not block so you will need to use
    asyncio's ``run_forever`` or a similar system ::

        >>> loop = asyncio.get_event_loop()
        >>> client = await Client('my_client', 'guest', 'localhost').start()
        >>> loop.run_forever()

    Parameters
    ----------
    name : str
        The name of the actor.
    url : str
        RFC3986 formatted broker address. When used, the other connection
        keyword arguments are ignored.
    user : str
        The user to connect to the AMQP broker. Defaults to ``guest``.
    password : str
        The password for the user. Defaults to ``guest``.
    host : str
        The host where the AMQP message broker runs. Defaults to ``localhost``.
    virtualhost : str
         Virtualhost parameter. ``'/'`` by default.
    port : int
        The port on which the AMQP broker is running. Defaults to 5672.
    ssl : bool
        Whether to use TLS/SSL connection.
    version : str
        The version of the actor.
    loop
        The event loop. If `None`, the current event loop will be used.
    log_dir : str
        The directory where to store the logs. Defaults to
        ``$HOME/logs/<name>`` where ``<name>`` is the name of the actor.
    log : ~logging.Logger
        A `~logging.Logger` instance to be used for logging instead of
        creating a new one.
    parser : ~clu.parser.CluGroup
        A click command parser that is a subclass of `~clu.parser.CluGroup`.
        If `None`, the active parser will be used.
    models : list
        A list of actor models whose schemas will be monitored.

    """

    __EXCHANGE_NAME__: str = ...

    connection = None
    def __init__(
        self,
        name: str,
        url: str | None = ...,
        user: str = ...,
        password: str = ...,
        host: str = ...,
        port: int = ...,
        virtualhost: str = ...,
        ssl: bool = ...,
        version: str | None = ...,
        loop: asyncio.AbstractEventLoop | None = ...,
        log_dir: str | None = ...,
        log: logging.Logger | None = ...,
        models: None = ...,
    ): ...
    async def start(self: T, exchange_name: str = ...) -> T:
        """Starts the connection to the AMQP broker."""
        ...
    async def stop(self):
        """Cancels queues and closes the connection."""
        ...
    async def run_forever(self):
        """Runs the event loop forever."""
        ...
    async def handle_reply(self, message: apika.IncomingMessage) -> AMQPReply:
        """Handles a reply received from the exchange.

        Creates a new instance of `.Reply` from the ``message``. If the
        reply is valid it updates any running command.

        Parameters
        ----------
        message : aio_pika.IncomingMessage
            The message received.

        Returns
        -------
        reply : `.AMQPReply`
            The `.AMQPReply` object created from the message.

        """
        ...
    async def send_command(
        self, consumer: str, command_string: str, command_id: str | None = ...
    ) -> Command:
        """Commands another actor over its RCP queue.

        Parameters
        ----------
        consumer : str
            The actor we are commanding.
        command_string : str
            The command string that will be parsed by the remote actor.
        command_id
            The command ID associated with this command. If empty, an unique
            identifier will be attached.

        """
        ...
