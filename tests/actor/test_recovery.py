#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-12-01
# @Filename: test_recovery.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import os.path
import pathlib

from typing import TYPE_CHECKING, Generator

import numpy
import pytest
from pytest_mock import MockerFixture

from clu import Command
from sdsstools import get_sjd

from archon.actor.actor import ArchonActor
from archon.actor.delegate import ExposureDelegate
from archon.actor.recovery import ExposureRecovery
from archon.exceptions import ArchonError


if TYPE_CHECKING:
    from archon.actor.delegate import FetchDataDict
    from archon.controller.controller import ArchonController


@pytest.fixture()
def exposure_recovery(controller: ArchonController, mocker: MockerFixture):
    mocker.patch.object(
        controller,
        "fetch",
        return_value=numpy.ones((1000, 3000)),
    )

    _exposure_recovery = ExposureRecovery({"sp1": controller})

    yield _exposure_recovery


@pytest.fixture()
def controller_info(test_config: dict) -> Generator[dict, None, None]:
    yield test_config["controllers"]


@pytest.fixture()
def fetch_data(tmp_path: pathlib.Path):
    _fetch_data: FetchDataDict = {
        "buffer": 1,
        "ccd": "r1",
        "controller": "sp1",
        "exposure_no": 1,
        "filename": str(tmp_path / "test.fits"),
        "data": numpy.array([]),
        "header": {
            "KEY1": ["value", "A comment"],
            "FILENAME": ["", ""],
            "EXPOSURE": ["", ""],
        },
    }

    yield _fetch_data


def test_recovery_update_unlink(
    exposure_recovery: ExposureRecovery,
    fetch_data: FetchDataDict,
):
    """Tests that the recovery is updated correctly."""

    exposure_recovery.update(fetch_data)
    assert os.path.exists(fetch_data["filename"] + ".lock")

    with pytest.raises(FileExistsError):
        exposure_recovery.unlink(fetch_data)

    exposure_recovery.unlink(fetch_data, force=True)
    assert not os.path.exists(fetch_data["filename"] + ".lock")


def test_recovery_update_unlink_filename(
    exposure_recovery: ExposureRecovery,
    fetch_data: FetchDataDict,
):
    exposure_recovery.update(fetch_data)
    assert os.path.exists(fetch_data["filename"] + ".lock")

    exposure_recovery.unlink(fetch_data["filename"])
    assert not os.path.exists(fetch_data["filename"] + ".lock")


async def test_recovery_update_recover(
    exposure_recovery: ExposureRecovery,
    fetch_data: FetchDataDict,
    controller_info: dict,
):
    exposure_recovery.update(fetch_data)
    lock_path = fetch_data["filename"] + ".lock"
    assert os.path.exists(lock_path)

    recovered = await exposure_recovery.recover(
        controller_info,
        files=[lock_path],
        write_checksum=True,
    )
    assert len(recovered) == 1

    filename = pathlib.Path(fetch_data["filename"])
    assert filename.exists()

    sjd = get_sjd()
    checksum_path = filename.parent / f"{sjd}.md5sum"
    assert checksum_path.exists()


async def test_recovery_lockfile_does_not_exist(
    exposure_recovery: ExposureRecovery,
    controller_info: dict,
    actor: ArchonActor,
):
    command = Command("", actor=actor)

    with exposure_recovery.set_command(command):
        results = await exposure_recovery.recover(
            controller_info,
            path="/bad/path/to/file.lock",
        )

    assert results == []
    assert "does not exist" in command.replies[-1].message["text"]


async def test_recovery_invalid_controller(
    exposure_recovery: ExposureRecovery,
    controller_info: dict,
    actor: ArchonActor,
    fetch_data: FetchDataDict,
):
    fetch_data["controller"] = "sp2"
    exposure_recovery.update(fetch_data)

    command = Command("", actor=actor)

    with exposure_recovery.set_command(command):
        results = await exposure_recovery.recover(
            controller_info,
            files=[fetch_data["filename"] + ".lock"],
        )

    assert results == []
    assert "Cannot find controller" in command.replies[-1].message["text"]


async def test_recovery_two_files(
    exposure_recovery: ExposureRecovery,
    controller_info: dict,
    fetch_data: FetchDataDict,
    tmp_path: pathlib.Path,
):
    fetch_data1 = fetch_data.copy()
    fetch_data2 = fetch_data.copy()

    fetch_data1["filename"] = str(tmp_path / "test_r1.fits")
    fetch_data1["ccd"] = "r1"

    fetch_data2["filename"] = str(tmp_path / "test_b1.fits")
    fetch_data1["ccd"] = "b1"

    exposure_recovery.update([fetch_data1, fetch_data2])

    recovered = await exposure_recovery.recover(controller_info, path=tmp_path)
    assert len(recovered) == 2

    assert os.path.exists(fetch_data1["filename"])
    assert os.path.exists(fetch_data2["filename"])


async def test_recovery_path_or_files(
    exposure_recovery: ExposureRecovery,
    controller_info: dict,
):
    with pytest.raises(ValueError):
        await exposure_recovery.recover(controller_info)


async def test_recovery_path_and_files(
    exposure_recovery: ExposureRecovery,
    controller_info: dict,
):
    with pytest.raises(ValueError):
        await exposure_recovery.recover(
            controller_info,
            path="/path/to/file",
            files=["/path/to/file"],
        )


async def test_recovery_excluded_cameras(
    exposure_recovery: ExposureRecovery,
    controller_info: dict,
    actor: ArchonActor,
    fetch_data: FetchDataDict,
):
    exposure_recovery.update(fetch_data)

    command = Command("", actor=actor)
    with exposure_recovery.set_command(command):
        results = await exposure_recovery.recover(
            controller_info,
            path=fetch_data["filename"] + ".lock",
            excluded_cameras=["r1"],
        )

    assert results == []
    assert "Skipping exposure" in command.replies[-1].message["text"]


async def test_recovery_failed_to_write(
    exposure_recovery: ExposureRecovery,
    controller_info: dict,
    actor: ArchonActor,
    fetch_data: FetchDataDict,
    mocker: MockerFixture,
):
    mocker.patch.object(
        ExposureDelegate,
        "write_to_disk",
        side_effect=ArchonError,
    )

    exposure_recovery.update(fetch_data)

    command = Command("", actor=actor)
    with exposure_recovery.set_command(command):
        results = await exposure_recovery.recover(
            controller_info,
            path=fetch_data["filename"] + ".lock",
        )

    assert results == []
    assert "Failed to write" in command.replies[-1].message["text"]
