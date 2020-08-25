#!/usr/bin/env python
"""Phoenix class to manage groups"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

from ClusterShell.NodeUtils import GroupSource
import phoenix

class Group(object):
    loaded_groups = False

    # Dicts to hold all System data
    groups = dict()

    @classmethod
    def load_groups(cls, filename=None):
        """ Reads and processes the groups.yaml file """
        if filename is None:
            filename = "%s/groups.yaml" % phoenix.conf_path

        # Read the yaml file
        logging.info("Loading group file '%s'", filename)
        with open(filename) as groupfd:
            cls.groups.update(load(groupfd, Loader=Loader))

    @classmethod
    def find_group(cls, group):
        if not cls.loaded_groups:
            cls.load_groups()
        if group[0] == '@':
            group = group[1:]
        return cls.groups[group]

    @classmethod
    def list_groups(cls):
        if not cls.loaded_groups:
            cls.load_groups()
        return sorted(cls.groups.keys())

class PhoenixGroupSource(GroupSource):
    def __init__(self):
        self.name = 'phoenix'

    def resolv_map(self, group):
        return Group.find_group(group)

    def resolv_list(self):
        return System.list_groups()
