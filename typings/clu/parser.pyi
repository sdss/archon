#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-05-06
# @Filename: parser.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from typing import Any, Callable

import click

from .command import Command

def coroutine(fn: Callable[[Any], Any]):
    """Create a coroutine. Avoids deprecation of asyncio.coroutine in 3.10."""
    ...

class CluCommand(click.Command):
    """Override :py:class:`click.Command` to pass the actor and command."""

    ...

class CluGroup(click.Group):
    """Override :py:class:`click.Group`.

    Makes all child commands instances of `.CluCommand`.

    """

    ...

def timeout(seconds: float) -> Any:
    """A decorator to timeout the command after a number of ``seconds``."""
    ...

def pass_args() -> Any:
    """Thing wrapper around pass_obj to pass the command and parser_args."""
    ...

@click.group(cls=CluGroup)
def command_parser(*args): ...
@command_parser.command()
def ping(*args):
    """Pings the actor."""
    ...

@command_parser.command()
def version(*args):
    """Reports the version."""
    ...

@command_parser.command(cls=CluCommand, name="get_schema")
def get_schema(*args):
    """Returns the schema of the actor as a JSON schema."""
    ...

@command_parser.command(name="help")
@click.argument("PARSER-COMMAND", type=str, required=False)
@click.pass_context
def help_(ctx, *args, parser_command: str):
    """Shows the help."""
    ...

class ClickParser:
    """A command parser that uses Click at its base."""

    #: list: Arguments to be passed to each command in the parser.
    #: Note that the command is always passed first.
    parser_args: list[Any] = []

    parser = command_parser
    def parse_command(self, command: Command) -> Command:
        """Parses an user command using the Click internals."""
        ...
