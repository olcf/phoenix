#!/usr/bin/env python
"""Phoenix class to manage networks"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

import phoenix
import ipaddress
from phoenix.system import System

class Network(object):
    loaded_config = False

    # Dicts to hold all Network data
    config = dict()

    @classmethod
    def load_config(cls, filename=None):
        """ Reads and processes the network.yaml file """
        if cls.loaded_config:
            return

        if filename is None:
            filename = "%s/network.yaml" % phoenix.conf_path

        # Read the yaml file
        logging.info("Loading network file '%s'", filename)
        try:
            with open(filename) as networkfd:
                cls.config = load(networkfd, Loader=Loader) or {}
                cls.loaded_config = True
                return
        except IOError:
            logging.error("%s does not exist", filename)

        try:
            cls.config = System.setting('networks')
            cls.loaded_config = True
        except KeyError:
            logging.error("Network settings not found in system either")

    @classmethod
    def _cache_network(cls, net):
        """ Cache a network definition """
        logging.debug("Caching network %s ip", net)

        # This is for python2/python3 compatability
        try:
            net2 = cls.config[net]['network'].decode()
        except:
            net2 = cls.config[net]['network']
        cls.config[net]['ipobj'] = ipaddress.ip_address(net2)

        # Cache the rack netmask width if present
        if 'rackmask' in cls.config[net]:
            netstring = "%s/%s" % ('0.0.0.0', cls.config[net]['rackmask'])
            try:
                netstring = netstring.decode()
            except:
                pass
            cls.config[net]['rackaddresses'] = ipaddress.ip_network(netstring).num_addresses
        else:
            cls.config[net]['rackaddresses'] = 0
        
    @classmethod
    def find_network(cls, net):
        """ Returns a tuple including:
            - ipaddress object responding to the base net
            - the number of addresses in the rack
        """
        if not cls.loaded_config:
            cls.load_config()

        # This is for python2/python3 compatability
        try:
            net = net.decode()
        except:
            pass

        if net not in cls.config:
            # Attempt to support an ip string instead of a defined network
            # Otherwise just return 0.0.0.0
            if net[0].isnumeric():
                return ipaddress.ip_address(net), 0
            else:
                return ipaddress.ip_address(0), 0

        if 'ipobj' not in cls.config[net]:
            cls._cache_network(net)

        return cls.config[net]['ipobj'], cls.config[net]['rackaddresses']

    @classmethod
    def ipadd(cls, base, offset, rack=0):
        logging.debug("Called ipadd with %s, offset %d, rack %d", base, offset,
                      rack)
        ip, rackaddresses = cls.find_network(base)
        return str(ip + offset + rack * rackaddresses)
