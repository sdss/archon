#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-22
# @Filename: maskbits.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import enum

__all__ = ["ModType"]


class ModType(enum.Enum):
    """Module type codes."""

    NONE = 0
    DRIVER = 1
    AD = 2
    LVBIAS = 3
    HVBIAS = 4
    HEATER = 5
    HS = 7
    HVXBIAS = 8
    LVXBIAS = 9
    LVDS = 10
    HEATERX = 11
    XVBIAS = 12
    ADF = 13
    ADX = 14
    ADLN = 15
    UNKNOWN = 16