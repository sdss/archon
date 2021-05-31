#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-30
# @Filename: wago.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List


if TYPE_CHECKING:
    from drift import Drift


async def read_many(devices: List[str], drift: Drift) -> List[Any]:
    """Reads a list of devices."""

    results = []

    async with drift:
        for device in devices:
            dev = drift.get_device(device)
            value = (await dev.read(connect=False))[0]
            results.append(value)

    return results
