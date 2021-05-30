#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-29
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from clu.actor import AMQPActor

from ..actor import ArchonActor
from ..actor.commands.expose import finish
from . import config
from .expose import lvm_post_process


class LVMActor(ArchonActor, AMQPActor):
    """LVM actor."""

    BASE_CONFIG = config


finish.callback.post_process = lvm_post_process
