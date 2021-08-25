#!/usr/bin/env python
"""Phoenix class to manage a System and plugin settings"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

from ClusterShell.NodeSet import NodeSet
import phoenix
import re
import copy

class System(object):
    loaded_config = False

    # Dicts to hold all System data
    config = dict()

    tpl_regex = re.compile(r'{{')

    @classmethod
    def load_config(cls, filename=None):
        """ Reads and processes the system.yaml file """
        if cls.loaded_config:
            return

        if filename is None:
            filename = "%s/system.yaml" % phoenix.conf_path

        # Read the yaml file
        logging.info("Loading system file '%s'", filename)
        with open(filename) as systemfd:
            systemdata = load(systemfd, Loader=Loader) or {}

        cls.config = systemdata
        cls.loaded_config = True

    @classmethod
    def setting(cls, key, default=None):
        if not cls.loaded_config:
            cls.load_config()
        try:
            return cls.config[key]
        except KeyError:
            return default
