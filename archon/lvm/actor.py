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
import warnings

from typing import TYPE_CHECKING, Dict

from astropy.io import fits
from astropy.time import Time
from authlib.integrations.httpx_client import AsyncAssertionClient

from archon.exceptions import ArchonWarning

from ..actor import ArchonActor
from . import config
from .commands import parser
from .delegate import LVMExposeDelegate
from .dli import DLI


try:
    from drift import Drift
except ImportError:
    raise ImportError("Cannot import sdss-drift. Did you install the lvm extra?")


if TYPE_CHECKING:
    from clu.model import Property


FILE_PATH = os.path.dirname(os.path.realpath(__file__))


class LVMActor(ArchonActor):
    """LVM actor."""

    BASE_CONFIG = config
    DELEGATE_CLASS = LVMExposeDelegate

    parser = parser

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self._log_lock = asyncio.Lock()
        self._log_values = {}

        assert self.model

        # Merge LVM schema with base schema.
        lvm_schema = os.path.join(FILE_PATH, "config/schema.json")
        lvm_schema = json.loads(open(lvm_schema, "r").read())
        schema = self.model.schema.copy()
        schema["definitions"].update(lvm_schema["definitions"])
        schema["properties"].update(lvm_schema["properties"])

        self.model.__init__("archon", schema, is_file=False)

        # Define Drift.
        self.drift: Dict[str, Drift] = {}
        if "devices" in self.config and "wago" in self.config["devices"]:
            wago_controllers = self.config["devices"]["wago"]["controllers"]
            modules = self.config["devices"]["wago"]["modules"]
            for controller in wago_controllers:
                wago_config = {**wago_controllers[controller], "modules": modules}
                self.drift[controller] = Drift.from_config(wago_config)

        # Add lamps
        self.dli = DLI()
        self.lamps: Dict[str, Dict] = {}
        self.add_lamps()

        # Add Google API client
        try:
            self.google_client = self.get_google_client()
        except Exception as err:
            warnings.warn(f"Failed authenticating with Google: {err}", ArchonWarning)
            self.google_client = None

        # Model callbacks
        self.model["filename"].register_callback(self.fill_log)

        # Timed commands
        self.timed_commands.add_command("lvm status", delay=30, first_silent=True)

    def add_lamps(self):
        """Adds the lamps."""

        if "lamps" not in self.config["devices"]:
            return

        if "credentials" not in self.config or "dli" not in self.config["credentials"]:
            warnings.warn(
                "Credentials for DLI not found. Lamps will not be loaded.",
                ArchonWarning,
            )

        for lamp in self.config["devices"]["lamps"]:
            host = self.config["devices"]["lamps"][lamp]["host"]

            if host not in self.dli.clients:
                if host not in self.config["credentials"]["dli"]:
                    warnings.warn(f"Missing credentials for DLI {host}.", ArchonWarning)
                    continue
                else:
                    cred = self.config["credentials"]["dli"][host]
                    self.dli.add_client(host, cred["user"], cred["password"])

            self.lamps[lamp] = self.config["devices"]["lamps"][lamp].copy()

    def get_google_client(self) -> AsyncAssertionClient | None:
        """Returns the client to communicate with the Google API."""

        credentials = self.config.get("credentials", None)
        if not credentials or "google" not in credentials:
            warnings.warn("No credentials for the Google API.", ArchonWarning)
            return None

        with open(credentials["google"]) as fd:
            conf = json.load(fd)

        token_uri = conf["token_uri"]
        header = {"alg": "RS256"}
        key_id = conf.get("private_key_id")
        if key_id:
            header["kid"] = key_id

        client = AsyncAssertionClient(
            token_endpoint=token_uri,
            issuer=conf["client_email"],
            audience=token_uri,
            claims={"scope": "https://www.googleapis.com/auth/spreadsheets"},
            subject=None,
            key=conf["private_key"],
            header=header,
        )

        return client

    def set_log_values(self, **values):
        """Sets additional values for the log."""

        self._log_values = values

    async def fill_log(self, key: Property):

        if not self.config.get("write_log", False):
            return

        if self.google_client is None or "exposure_list_sheet" not in self.config:
            return

        path = key.value
        if not os.path.exists(path):
            self.write(
                "w",
                error=f"File {path} not found. Cannot write lab log entry.",
            )
            return

        header = fits.getheader(path)

        filename = os.path.basename(path)

        match = re.match(r".+-([0-9]+)\.fits(?:\.gz)$", filename)
        assert match

        exp_no = int(match.group(1))

        obsdate = Time(header["OBSTIME"], format="isot")
        mjd = int(obsdate.mjd)
        date_str = obsdate.strftime("%d/%m/%Y")
        location = "SBS"
        spec = header["SPEC"]
        channel = header["CCD"]
        exptime = header["EXPTIME"]

        lamp_sources = []
        for lamp in self.lamps:
            if lamp.upper() in header and header[lamp.upper()] == "ON":
                lamp_sources.append(lamp)
        lamp_sources = " ".join(lamp_sources)

        hartmanns = "?"
        if "HARTMANN" in header:
            if header["HARTMANN"].strip() == "0 1":
                hartmanns = "R"
            elif header["HARTMANN"].strip() == "1 0":
                hartmanns = "L"
            elif header["HARTMANN"].strip() == "1 1":
                hartmanns = "L R"
            elif header["HARTMANN"].strip() == "0 0":
                hartmanns = ""

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
            hartmanns,
            exptime,
            lab_temp,
            ccd_temp,
            purpose,
            notes,
        )

        self._log_values = {}

        google_data = {
            "range": "Sheet1!A1:A1",
            "majorDimension": "ROWS",
            "values": [data],
        }

        spreadsheet_id = self.config["exposure_list_sheet"]
        r = await self.google_client.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/"
            "values/Sheet1!A1:A1:append?valueInputOption=USER_ENTERED",
            json=google_data,
        )

        if not r.status_code == 200:
            warnings.warn("Failed writing exposure to spreadsheet.", ArchonWarning)
