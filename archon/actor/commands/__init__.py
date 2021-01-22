#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import glob
import importlib
import os
import warnings

import click
from clu.parser import CluGroup, help_, ping, version

from archon.exceptions import ArchonUserWarning


@click.group(cls=CluGroup)
def parser(*args):
    pass


parser.add_command(ping)
parser.add_command(version)
parser.add_command(help_)


# Autoimport all modules in this directory so that they are added to the parser.

exclusions = ["__init__.py"]

cwd = os.getcwd()
os.chdir(os.path.dirname(os.path.realpath(__file__)))

files = [
    file_ for file_ in glob.glob("**/*.py", recursive=True) if file_ not in exclusions
]

for file_ in files:
    modname = file_[0:-3].replace("/", ".")
    mod = importlib.import_module("archon.actor.commands." + modname)

os.chdir(cwd)
