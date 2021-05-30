#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-29
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from typing import List, Tuple

from astropy.io import fits
from clu.actor import AMQPActor, Command

from archon.controller.controller import ArchonController

from ..actor import ArchonActor
from ..actor.commands.expose import finish
from . import config
from .tools import read_govee


class LVMActor(ArchonActor, AMQPActor):
    """LVM actor."""

    BASE_CONFIG = config


async def lvm_post_process(
    command: Command,
    controller: ArchonController,
    hdus: List[fits.PrimaryHDU],
) -> Tuple[ArchonController, List[fits.PrimaryHDU]]:

    try:
        temp, hum = await read_govee()
    except BaseException as err:
        command.warning(text=f"Failed retriving H5179 data: {err}")
        temp = -999.0
        hum = -999.0

    for hdu in hdus:
        hdu.header["LABTEMP"] = (temp, "Govee H5179 lab temperature [C]")
        hdu.header["LABHUMID"] = (hum, "Govee H5179 lab humidity [%]")

    return (controller, hdus)


finish.callback.post_process = lvm_post_process
