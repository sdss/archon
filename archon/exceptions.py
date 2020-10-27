# !usr/bin/env python
# -*- coding: utf-8 -*-
#
# Licensed under a 3-clause BSD license.
#
# @Author: Brian Cherinka
# @Date:   2017-12-05 12:01:21
# @Last modified by:   Brian Cherinka
# @Last Modified time: 2017-12-05 12:19:32


class ArchonError(Exception):
    """A custom core Archon exception"""


class ArchonWarning(Warning):
    """Base warning for Archon."""


class ArchonUserWarning(UserWarning, ArchonWarning):
    """The primary warning class."""
    pass
