#!/usr/bin/env python
"""Phoenix class to manage a System (its config and nodes)"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

from ClusterShell.NodeSet import NodeSet
from ClusterShell.NodeUtils import GroupSource
import Phoenix
import re
import copy
import ipaddress

class System(object):
    loaded_config = False
    loaded_groups = False

    # Dicts to hold all System data
    config = dict()
    groups = dict()

    tpl_regex = re.compile(r'{{')

    @classmethod
    def load_config(cls, filename=None):
        """ Reads and processes the system.yaml file """
        if filename is None:
            filename = "%s/system.yaml" % Phoenix.conf_path

        # Read the yaml file
        logging.info("Loading system file '%s'", filename)
        with open(filename) as systemfd:
            systemdata = load(systemfd, Loader=Loader)

        cls.config = systemdata
        cls.loaded_config = True

    @classmethod
    def find_network(cls, net):
        """ Returns a network in ipaddress format """
        if not cls.loaded_config:
            cls.load_config()

        if net not in cls.config['networks']:
            # Attempt to support an ip string, otherwise just return 0.0.0.0
            if unicode(net[0], 'utf-8').isnumeric():
                return ipaddress.ip_address(unicode(net, "utf-8")) 
            else:
                return ipaddress.ip_address(0)

        if 'ipobj' not in cls.config['networks'][net]:
            logging.debug("Caching network %s ip", net)
            cls.config['networks'][net]['ipobj'] = ipaddress.ip_address(unicode(cls.config['networks'][net]['network'], "utf-8"))

        return cls.config['networks'][net]['ipobj']

    @classmethod
    def load_groups(cls, filename=None):
        """ Reads and processes the groups.yaml file """
        if filename is None:
            filename = "%s/groups.yaml" % Phoenix.conf_path

        # Read the yaml file
        logging.info("Loading group file '%s'", filename)
        with open(filename) as nodefd:
            cls.groups.update(load(nodefd, Loader=Loader))

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
        return System.find_group(group)

    def resolv_list(self):
        return System.list_groups()
