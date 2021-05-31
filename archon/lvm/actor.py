#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-29
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from ..actor import ArchonActor
from . import config
from .expose import LVMExposeDelegate


class LVMActor(ArchonActor):
    """LVM actor."""

    BASE_CONFIG = config
    DELEGATE_CLASS = LVMExposeDelegate
