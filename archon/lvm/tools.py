#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-29
# @Filename: tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


from __future__ import annotations

import asyncio
import re

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

    writer.close()
    await writer.wait_closed()

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


async def read_pressure(host: str, port: int, id: int, read_timeout=5) -> bool | float:
    """Reads pressure from a SENS4 device."""

    w = None

    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), 1)

        w.write(b"@" + str(id).encode() + b"P?\\")
        await w.drain()

        reply = await asyncio.wait_for(r.readuntil(b"\\"), read_timeout)
        match = re.search(r"@[0-9]{1,3}ACK([0-9.E+-]+)\\$".encode(), reply)

        if not match:
            return False

        return float(match.groups()[0])
    except Exception:
        return False
    finally:
        if w is not None:
            w.close()
            await w.wait_closed()
