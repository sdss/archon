#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-29
# @Filename: tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


from __future__ import annotations

import asyncio

from typing import Tuple

import astropy.time

from . import config


__all__ = ["read_govee"]


async def read_govee() -> Tuple[float, float]:
    """Connects to the H5179 device and gets the lab temperature and humidity."""

    h5179 = config["sensors"]["H5179"]
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(h5179["host"], h5179["port"]),
        timeout=2,
    )
    writer.write(b"status\n")
    await writer.drain()

    data = await asyncio.wait_for(reader.readline(), timeout=5)
    lines = data.decode().strip().splitlines()

    temp = hum = last = None
    for line in lines:
        name, temp, hum, __, last = line.split()
        if name == "H5179":
            break

    if temp is None or hum is None or last is None:
        raise ValueError("Did not get a measurement for H5179.")

    temp = float(temp)
    hum = float(hum)

    last_seen = astropy.time.Time(last, format="isot")
    delta = astropy.time.Time.now() - last_seen
    if delta.datetime.seconds / 60 > 10:
        raise RuntimeError("Lab metrology is over 10 minutes old.")

    return temp, hum
