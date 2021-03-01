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
        if cls.loaded_config:
            return

        if filename is None:
            filename = "%s/system.yaml" % phoenix.conf_path

        # Read the yaml file
        logging.info("Loading system file '%s'", filename)
        with open(filename) as systemfd:
            systemdata = load(systemfd, Loader=Loader)

        cls.config = systemdata
        cls.loaded_config = True

    @classmethod
    def setting(cls, key):
        if not cls.loaded_config:
            cls.load_config()
        return cls.config[key]

    @classmethod
    def find_network(cls, net):
        """ Returns a network in ipaddress format """
        if not cls.loaded_config:
            cls.load_config()

        # This is for python2/python3 compatability
        try:
            net = net.decode()
        except:
            pass

        if net not in cls.config['networks']:
            # Attempt to support an ip string, otherwise just return 0.0.0.0
            if net[0].isnumeric():
                return ipaddress.ip_address(net) 
            else:
                return ipaddress.ip_address(0)

        if 'ipobj' not in cls.config['networks'][net]:
            logging.debug("Caching network %s ip", net)

            # This is for python2/python3 compatability
            try:
                net2 = cls.config['networks'][net]['network'].decode()
            except:
                net2 = cls.config['networks'][net]['network']
            cls.config['networks'][net]['ipobj'] = ipaddress.ip_address(net2)

        return cls.config['networks'][net]['ipobj']
