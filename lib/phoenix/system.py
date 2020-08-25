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
import phoenix
import re
import copy
import ipaddress

class System(object):
    loaded_config = False

    # Dicts to hold all System data
    config = dict()

    tpl_regex = re.compile(r'{{')

    @classmethod
    def load_config(cls, filename=None):
        """ Reads and processes the system.yaml file """
        if filename is None:
            filename = "%s/system.yaml" % phoenix.conf_path

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
