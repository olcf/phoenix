#!/usr/bin/env python
"""Generic Data Source Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import sys
from Phoenix.System import System

class DataSource(object):
    @classmethod
    def getval(cls, *args):
        raise NotImplementedError

    @classmethod
    def setval(cls, *args):
        raise NotImplementedError

def load_datasource():
    System.load_config()
    try:
        source = System.config['datasource']
    except KeyError:
        source = 'csv'

    classname = source.lower().capitalize()
    modname = "Phoenix.DataSource.%s" % classname

    # Iterate over a copy of sys.modules' keys to avoid RuntimeError
    if modname.lower() not in [mod.lower() for mod in list(sys.modules)]:
        # Import module if not yet loaded
        __import__(modname)

    # Get the class pointer
    try:
        return getattr(sys.modules[modname], classname + 'DataSource')
    except:
        raise ImportError("Could not find class %s" % classname)

