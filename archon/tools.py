#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-20
# @Filename: tools.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

__all__ = ["Timer"]


class Timer:
    """An asynchronous timer."""

    def __init__(self, timeout: float, callback):
        self._timeout = timeout
        self._callback = callback

        self._loop = asyncio.get_event_loop()
        self._task: asyncio.Task | None = None

        self.reset()

    async def _job(self):
        await asyncio.sleep(self._timeout)
        try:
            await self._callback()
        except TypeError:  # Happens when the callback becomes None during an error.
            pass

    def cancel(self):
        """Cancel the timer."""
        if self._task:
            self._task.cancel()

    def reset(self):
        """Reset the count."""
        self.cancel()
        self._task = self._loop.create_task(self._job())
