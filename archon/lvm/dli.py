#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-31
# @Filename: dli.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import Dict

import httpx


__all__ = ["DLI"]


class DLI(object):
    """Controller for the Digital Loggers Inc power supply."""

    def __init__(self):
        self.clients = {}

    def add_client(self, host: str, user: str, password: str):
        """Adds a client."""

        auth = httpx.DigestAuth(user, password)
        self.clients[host] = httpx.AsyncClient(
            auth=auth,
            base_url=f"http://{host}/restapi",
            headers={},
        )

    async def get_outlet_state(self, host: str, outlet: int) -> bool:
        """Gets the value of the outlet (1-indexed)."""

        outlet -= 1

        if host not in self.clients:
            raise ValueError(f"Client for host {host} not defined.")

        r = await self.clients[host].get(f"relay/outlets/{outlet}/state/")
        if r.status_code != 200:
            raise RuntimeError(f"GET returned code {r.status_code}.")

        return r.json()

    async def set_outlet_state(self, host: str, outlet: int, value: bool):
        """Gets the value of the outlet (1-indexed)."""

        outlet -= 1

        if host not in self.clients:
            raise ValueError(f"Client for host {host} not defined.")

        client = self.clients[host]

        r = await client.put(
            f"relay/outlets/{outlet}/state/",
            data={"value": value},
            headers={"X-CSRF": "x"},
        )
        if r.status_code != 204:
            raise RuntimeError(f"PUT returned code {r.status_code}.")

        return

    async def report_lamps(
        self,
        command,
        lamp_names=None,
        write=True,
    ) -> Dict[str, bool]:
        """Returns a dictionary of lamp statues."""

        actor = command.actor
        assert actor.dli == self

        if lamp_names is None:
            lamps = actor.lamps
        else:
            lamps = {name: actor.lamps[name] for name in lamp_names}

        jobs = []
        for name, data in lamps.items():
            jobs.append(
                asyncio.create_task(
                    self.get_outlet_state(
                        data["host"],
                        data["outlet"],
                    )
                )
            )
        await asyncio.gather(*jobs, return_exceptions=True)

        lamps_dict = {}
        keys = list(lamps.keys())
        for ii, job in enumerate(jobs):
            lname = keys[ii]
            if job.exception() is not None:
                command.warning(f"Status of lamp {lname} cannot be retrieved.")
                continue
            lamps_dict[lname] = job.result()

        if write:
            command.info(lamps=lamps_dict)

        return lamps_dict
