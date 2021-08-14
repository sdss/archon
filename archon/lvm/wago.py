#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-30
# @Filename: wago.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from drift import DriftError


if TYPE_CHECKING:
    from clu import Command
    from drift import Drift


async def read_many(command: Command, devices: List[str], drift: Drift) -> Dict:
    """Reads a list of devices."""

    results = {}

    try:
        async with drift:
            for device in devices:
                dev = drift.get_device(device)
                value = (await dev.read(connect=False))[0]
                results[device.lower()] = value
    except DriftError as err:
        command.warning(text=f"Failed connecting to WAGO: {err}")
        return results

    return results
