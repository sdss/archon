#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-05-29
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os

from sdsstools.configuration import Configuration

from .. import config as archon_config


# Load the custom configuration.
cwd = os.path.dirname(os.path.realpath(__file__))
config = Configuration(
    config=os.path.join(cwd, "config/lvm.yaml"),
    base_config=archon_config,
)


from .actor import LVMActor
