#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-03
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os
import pathlib

import clu.testing
import numpy
import pytest
from clu.actor import AMQPBaseActor

from sdsstools import merge_config, read_yaml_file

from archon import config
from archon.actor import ArchonActor
from archon.controller.controller import ArchonController


@pytest.fixture()
def test_config():

    extra = read_yaml_file(os.path.join(os.path.dirname(__file__), "config.yaml"))
    yield merge_config(extra, config)


@pytest.fixture()
async def actor(test_config: dict, controller: ArchonController, mocker):

    # We need to call the actor .start() method to force it to create the
    # controllers and to start the tasks, but we don't want to run .start()
    # on the actor.
    mocker.patch.object(AMQPBaseActor, "start")

    test_config["controllers"]["sp1"]["host"] = controller.host
    test_config["controllers"]["sp1"]["port"] = controller.port

    _actor = ArchonActor.from_config(test_config)
    _actor.controllers["sp1"].acf_loaded = test_config["archon"]["config_file"]
    await _actor.start()

    _actor = await clu.testing.setup_test_actor(_actor)  # type: ignore

    yield _actor

    _actor.mock_replies.clear()
    await _actor.stop()


@pytest.fixture()
def delegate(actor: ArchonActor, monkeypatch, tmp_path: pathlib.Path, mocker):

    mocker.patch.object(actor.controllers["sp1"], "readout")

    mocker.patch.object(
        actor.controllers["sp1"],
        "fetch",
        return_value=numpy.ones((1024, 12288)),
    )

    assert actor.model
    actor.model["status"].value = {
        "controller": "sp1",
        "mod2/tempa": -110,
        "mod2/tempb": -110,
        "mod2/tempc": -110,
        "mod12/tempa": -110,
        "mod12/tempb": -110,
        "mod12/tempc": -110,
    }

    files_data_dir = tmp_path / "archon"

    monkeypatch.setitem(actor.config["files"], "data_dir", str(files_data_dir))

    yield actor.expose_delegate
