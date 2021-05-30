#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-29
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import json
import os
import re

from typing import TYPE_CHECKING

from astropy.io import fits
from astropy.time import Time

from ..actor import ArchonActor
from . import config
from .commands import parser
from .expose import LVMExposeDelegate


try:
    from drift import Drift
except ImportError:
    raise ImportError("Cannot import sdss-drift. Did you install the lvm extra?")


if TYPE_CHECKING:
    from clu.model import Property


class LVMActor(ArchonActor):
    """LVM actor."""

    BASE_CONFIG = config
    DELEGATE_CLASS = LVMExposeDelegate

    parser = parser

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._log_lock = asyncio.Lock()
        self._log_values = {}

        self.drift: Drift | None = None

    async def start(self):

        # Merge LVM schema with base schema.
        lvm_schema = json.loads(
            open(
                os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    "config/schema.json",
                ),
                "r",
            ).read()
        )
        schema = self.model.schema.copy()
        schema["properties"].update(lvm_schema["properties"])

        self.model.__init__("archon", schema, is_file=False)

        # Define Drift. This needs to happen here because __init__ is not
        # aware of the configuration until after from_config appends it.
        if "devices" in self.config and "wago" in self.config["devices"]:
            self.drift = Drift.from_config(self.config["devices"]["wago"])

        await super().start()

        self.model["filename"].register_callback(self.fill_log)

        return self

    def set_log_values(self, **values):
        """Sets additional values for the log."""

        self._log_values = values

    async def fill_log(self, key: Property):

        if not self.config.get("write_log", False):
            return

        path = key.value
        if not os.path.exists(path):
            self.write(
                "w",
                error=f"File {path} not found. Cannot write lab log entry.",
            )
            return

        header = fits.getheader(path)
        lab_log_path = self.config["files"]["lab_log"]

        filename = os.path.basename(path)
        exp_no = int(re.match(r".+-([0-9]+)\.fits(?:\.gz)$", filename).group(1))

        obsdate = Time(header["OBSTIME"], format="isot")
        mjd = int(obsdate.mjd)
        date_str = obsdate.strftime("%d/%m/%Y")
        location = "SBS"
        spec = header["SPEC"]
        channel = header["CCD"]
        exptime = header["EXPTIME"]

        lamp_sources = self._log_values.get("lamp_sources", "")
        lamp_current = self._log_values.get("lamp_current", "")
        lab_temp = header["LABTEMP"]
        ccd_temp = header["CCDTEMP1"]

        purpose = self._log_values.get("purpose", "")
        notes = self._log_values.get("notes", "")

        test_no = self._log_values.get("test_no", "")
        test_iteration = self._log_values.get("test_iteration", "")

        data = (
            exp_no,
            filename,
            mjd,
            date_str,
            location,
            test_no,
            test_iteration,
            spec,
            channel,
            lamp_sources,
            lamp_current,
            exptime,
            lab_temp,
            ccd_temp,
            purpose,
            notes,
        )

        async with self._log_lock:
            with open(lab_log_path, "a") as log:
                log.write(",".join(map(str, data)) + "\n")
