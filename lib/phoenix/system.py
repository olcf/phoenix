#!/usr/bin/env python3
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
    loaded_racklist = False

    # Dicts to hold all System data
    config = dict()
    rackmap = dict()

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
    def load_racklist(cls):
        ''' Special handling for 'racks'. Expected to be a map with keys being
            "categories" of racks, and the values being ordered lists of
             NodeSet strings. Caches this as category to expanded list
        '''
        if cls.loaded_racklist:
            return

        if 'racks' not in cls.config:
            cls.loaded_racklist = True
            return

        if not isinstance(cls.config['racks'], dict):
            raise KeyError("system.yaml 'racks' must be a mapping")
        for category, value in cls.config['racks'].items():
            if isinstance(value, str):
                value = [value]
            racklist = list()
            for entry in value:
                racklist.extend(list(NodeSet(entry)))
            cls.rackmap[category] = racklist
        cls.loaded_racklist = True

    @classmethod
    def racklist(cls, category):
        if not cls.loaded_racklist:
            cls.load_racklist()

        if category not in cls.rackmap:
            raise KeyError("Rack category '%s' not found in system.yaml" % category)

        return cls.rackmap[category]

    @classmethod
    def rackindex(cls, category, needle):
        return cls.racklist(category).index(needle)

    @classmethod
    def setting(cls, key, default=None):
        if not cls.loaded_config:
            cls.load_config()
        try:
            return cls.config[key]
        except KeyError:
            return default
