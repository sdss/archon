#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-24
# @Filename: test_config.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from typing import Callable, Optional

import pytest

import archon.controller.controller
from archon.controller.command import (
    ArchonCommand,
    ArchonCommandReply,
    ArchonCommandStatus,
)
from archon.controller.controller import ArchonController
from archon.exceptions import ArchonError

pytestmark = [pytest.mark.asyncio]


# Make tests faster by faking the number of config lines
archon.controller.controller.MAX_CONFIG_LINES = 5


def send_command(parser: Optional[Callable[[ArchonCommand], ArchonCommand]] = None):
    def default_parser(cmd: ArchonCommand):
        if cmd.command_string == "SYSTEM":
            cmd._mark_done()
            cmd.replies = [ArchonCommandReply(b"<00SYSTEM=0", cmd)]
            return cmd

        r_n = int(cmd.command_string[7:11], 16)
        cmd._mark_done()
        if r_n < 5:
            reply = f"<{r_n:02X}LINE{r_n}={r_n}\n"
        else:
            reply = f"<{r_n:02X}\n"
        cmd.replies = [ArchonCommandReply(reply.encode(), cmd)]
        return cmd

    def send_command_internal(cmd_str: str, **kwargs):
        cmd = ArchonCommand(cmd_str, 0)
        (parser or default_parser)(cmd)
        return cmd

    return send_command_internal


async def test_read_config(controller: ArchonController, mocker):
    mocker.patch.object(
        ArchonController,
        "send_command",
        side_effect=send_command(),
    )

    config = await controller.read_config()
    assert len(config) == 5
    assert config[0] == "LINE0=0"


async def test_read_config_fails(controller: ArchonController, mocker):
    def parser(cmd: ArchonCommand):
        cmd._mark_done(ArchonCommandStatus.FAILED)
        cmd.replies = []
        return cmd

    mocker.patch.object(
        ArchonController,
        "send_command",
        side_effect=send_command(parser),
    )

    with pytest.raises(ArchonError):
        await controller.read_config()


async def test_read_config_no_reply(controller: ArchonController, mocker):
    def parser(cmd: ArchonCommand):
        cmd._mark_done(ArchonCommandStatus.DONE)
        cmd.replies = []
        return cmd

    mocker.patch.object(
        ArchonController,
        "send_command",
        side_effect=send_command(parser),
    )

    with pytest.raises(ArchonError):
        await controller.read_config()


@pytest.mark.parametrize("path", [True, "/home/test/test.acf"])
async def test_read_config_save(controller: ArchonController, mocker, path):
    mocker.patch.object(
        ArchonController,
        "send_command",
        side_effect=send_command(),
    )

    open_patch = mocker.patch("builtins.open")

    config = await controller.read_config(save=path)
    assert len(config) == 5
    assert config[0] == "LINE0=0"

    assert open_patch.called_once()


@pytest.fixture()
def config_file(tmp_path):
    config_ = tmp_path / "config.acf"
    with open(config_, "w") as f:
        f.write(
            r"""[CONFIG]
CONFIG\1=1
CONFIG\2="2,2"
"""
        )

    yield config_


async def test_write_config(controller: ArchonController, mocker, config_file):
    def parser(cmd: ArchonCommand):
        cmd._mark_done()
        reply = f"<{cmd.command_id:02X}\n"
        cmd.replies = [ArchonCommandReply(reply.encode(), cmd)]
        return cmd

    mocker.patch.object(
        ArchonController,
        "send_command",
        side_effect=send_command(parser),
    )

    await controller.write_config(config_file, applyall=True, poweron=True)


async def test_write_config_no_config(controller: ArchonController, tmp_path):
    empty_file = tmp_path / "empty.acf"
    empty_file.touch()

    with pytest.raises(ArchonError):
        await controller.write_config(empty_file)


@pytest.mark.commands([["CLEARCONFIG", ["?{cid}"]]])
async def test_write_config_clear_fails(controller: ArchonController, config_file):
    with pytest.raises(ArchonError) as err:
        await controller.write_config(config_file)
    assert "Failed running CLEARCONFIG." in str(err)


@pytest.mark.commands([["WCONFIG", ["?{cid}"]], ["CLEARCONFIG", ["<{cid}"]]])
async def test_write_config_wconfig_fails(controller: ArchonController, config_file):
    with pytest.raises(ArchonError) as err:
        await controller.write_config(config_file)
    assert "Failed sending line" in str(err)


async def test_write_config_applyall_fails(
    controller: ArchonController,
    mocker,
    config_file,
):
    def parser(cmd: ArchonCommand):
        if cmd.command_string == "APPLYALL":
            reply = f"?{cmd.command_id:02X}\n"
            cmd._mark_done(ArchonCommandStatus.FAILED)
        else:
            reply = f"<{cmd.command_id:02X}\n"
            cmd._mark_done()
        cmd.replies = [ArchonCommandReply(reply.encode(), cmd)]
        return cmd

    mocker.patch.object(
        ArchonController,
        "send_command",
        side_effect=send_command(parser),
    )

    with pytest.raises(ArchonError) as err:
        await controller.write_config(config_file, applyall=True)
    assert "Failed sending APPLYALL" in str(err)


async def test_write_config_poweron_fails(
    controller: ArchonController,
    mocker,
    config_file,
):
    def parser(cmd: ArchonCommand):
        if cmd.command_string == "POWERON":
            reply = f"?{cmd.command_id:02X}\n"
            cmd._mark_done(ArchonCommandStatus.FAILED)
        else:
            reply = f"<{cmd.command_id:02X}\n"
            cmd._mark_done()
        cmd.replies = [ArchonCommandReply(reply.encode(), cmd)]
        return cmd

    mocker.patch.object(
        ArchonController,
        "send_command",
        side_effect=send_command(parser),
    )

    with pytest.raises(ArchonError) as err:
        await controller.write_config(config_file, applyall=True, poweron=True)
    assert "Failed sending POWERON" in str(err)
