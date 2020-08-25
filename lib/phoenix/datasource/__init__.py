#!/usr/bin/env python
"""Generic Data Source Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import sys
import phoenix
from phoenix.system import System

class Datasource(object):
    @classmethod
    def getval(cls, *args):
        raise NotImplementedError

    @classmethod
    def setval(cls, *args):
        raise NotImplementedError

DEFAULT_PROVIDER='csvfile'
