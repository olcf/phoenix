#!/usr/bin/env python3
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
from phoenix.data import Data

class Network(object):
    loaded_config = False

    # Dicts to hold all Network data
    config = dict()

    @classmethod
    def load_config(cls, filename=None):
        """ Reads and processes the networks.yaml file """
        if cls.loaded_config:
            return

        if filename is None:
            filename = "%s/networks.yaml" % phoenix.conf_path

        # Read the yaml file
        logging.info("Loading network file '%s'", filename)
        try:
            with open(filename) as networkfd:
                cls.config = load(networkfd, Loader=Loader) or {}
                for network in cls.config:
                    cls._cache_network(network)
                cls.loaded_config = True
                return
        except IOError:
            logging.error("%s does not exist", filename)

        try:
            cls.config = System.setting('networks')
            for network in cls.config:
                cls._cache_network(network)
            cls.loaded_config = True
        except KeyError:
            logging.error("Network settings not found in system either")

    @classmethod
    def _cache_network(cls, net):
        """ Parse and cache a network definition """
        if 'network' in cls.config[net]:
            cls._cache_network_family(net, family=4)
        if 'network6' in cls.config[net]:
            cls._cache_network_family(net, family=6)

    @classmethod
    def _cache_network_family(cls, net, family=4):
        """ Parse and cache a network ipv4 definition """
        logging.debug("Caching network %s ipv%d details", (net, family))
        cfg = cls.config[net]

        # To support both ipv4 and ipv6, create a mapping 't' from the ipv4
        # key to the (ipv4 or ipv6) key
        entities = ['network', 'prefix', 'netmask', 'ipobj', 'rackprefix', 'rackmask', 'racknetmask', 'subnets', 'rackaddresses', 'rackprefixlen']
        if family == 4:
            t = {a:a for a in entities}
        else:
            t = {a:a+'6' for a in entities}
            t['ipobj'] = 'ip6obj'

        # Create an ip_network object based on the network and netmask
        if '/' in cfg[t['network']]:
            ipobj = ipaddress.ip_network(cfg[t['network']])
        elif t['prefix'] in cfg:
            ipobj = ipaddress.ip_network((cfg[t['network']], cfg[t['prefix']]))
        elif t['netmask'] in cfg:
            ipobj = ipaddress.ip_network((cfg[t['network']], cfg[t['netmask']]))
        else:
            raise ValueError("Network %s must have an ipv%d netmask or prefix" % (net, family))

        # Store the ipobj, network, netmask, and prefix
        cfg[t['ipobj']] = ipobj
        cfg[t['network']] = str(ipobj.network_address)
        cfg[t['netmask']] = str(ipobj.netmask)
        cfg[t['prefix']] = str(ipobj.prefixlen)

        # Cache the rack netmask width if present
        if t['rackprefix'] in cfg or t['rackmask'] in cfg or t['racknetmask'] in cfg:
            if t['rackprefix'] in cfg:
                prefix = cfg[t['rackprefix']]
            elif t['racknetmask'] in cfg:
                prefix = cfg[t['racknetmask']]
            else:
                prefix = cfg[t['rackmask']]

            subnets = list(ipobj.subnets(new_prefix=prefix))
            cfg[t['subnets']] = subnets

            cfg[t['rackaddresses']] = subnets[0].num_addresses
            cfg[t['racknetmask']] = subnets[0].netmask
            cfg[t['rackprefixlen']] = subnets[0].prefixlen
        else:
            cfg[t['rackaddresses']] = 0
            cfg[t['subnets']] = [ipobj]

    @classmethod
    def networks(cls):
        ''' Returns the dict of networks '''
        if not cls.loaded_config:
            cls.load_config()

        return cls.config

    @classmethod
    def find_network(cls, net):
        """ Returns the network as a dict. If an IP was provided instead,
            it returns a dict including:
            - ipobj - responding to the base net
            - rackaddresses - the number of addresses in the rack
        """
        if not cls.loaded_config:
            cls.load_config()

        if net not in cls.config:
            # Attempt to support an ip string instead of a defined network
            if net[0].isnumeric():
                return { 'network': net,
                         ipobj: ipaddress.ip_network(net),
                         rackaddresses: 0
                       }
            else:
                raise KeyError("Network '%s' is not defined in networks.yaml" % net)

        if 'ipobj' not in cls.config[net]:
            cls._cache_network(net)

        return cls.config[net]

    @classmethod
    def ipadd(cls, base, offset, rack=0, family=None):
        logging.debug("Called ipadd with %s, offset %d, rack %d, family %s",
                      base, offset, rack, family)
        net = cls.find_network(base)
        if family is None:
            if 'network' in net:
                family = 4
            elif 'network6' in net:
                family = 6
        if (family == 4 and 'ipobj' not in net) or (family == 6 and 'ip6obj' not in net):
            logging.error("No ipv%d network found in network %s" % (family, base))
            return "error"
        if family == 4:
            subnet = net['subnets'][rack]
        else:
            subnet = net['subnets6'][rack]
        return str(subnet.network_address + offset)

def handleautointerfaces(node):
    # autointerfaces
    # Format: interface,network,ipoffset[,key=value[,key2=value2]][;interface,network,ipoffset[,key=value]]
    # For keys, the following have special meaning:
    # - mac=<dataname> Pull the value from a data plugin with the key dataname
    if 'autointerfaces' not in node:
        return
    autointerfaces = node['autointerfaces']
    if autointerfaces is None:
        return
    result = dict()
    for entry in autointerfaces.split(';'):
        components = entry.split(',')
        iface = components[0]
        result[iface] = dict()
        result[iface]['network'] = components[1]
        result[iface]['ip'] = Network.ipadd(components[1], node['nodeindex'] + int(components[2]))
        for i in range(3, len(components)):
            entities = components[i].split("=", 1)
            if entities[0] == "mac":
                result[iface]['mac'] = lambda key=entities[1],name=node['name']: Data.data(key, name)
            else:
                if '+' in entities[1]:
                    result[iface][entities[0]] = entities[1].split('+')
                else:
                    result[iface][entities[0]] = entities[1]
    node.setrawitem('interfaces', result)
    node.setcache('autointerfaces', None)
