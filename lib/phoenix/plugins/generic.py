#!/usr/bin/env python
"""Generic Plugin run on systems/nodes without an explicit plugin defined"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import re
from phoenix.system import System
from phoenix.network import Network
from phoenix.node import Node
num_regex = re.compile(r'\d+')
logging.debug("Generic plugin compiled the num_regex")

def set_node_attrs(node, alias=None):
    logging.debug("Running generic plugin for node %s" % (node['name']))

    # Extract node index number from the name
    m = num_regex.findall(node['name'])
    if m is not None and len(m) > 0:
        node['nodeindex'] = int(m[-1])
        if len(m) > 1:
            node['nodenums'] = [ int(x) for x in m ]

    if 'autointerfaces' in node:
        handleautointerfaces(node)

def handleautointerfaces(node):
    # autointerfaces
    # Format: interface,network,ipoffset[,key=value[,key2=value2]][;interface,network,ipoffset[,key=value]]
    # For keys, the following have special meaning:
    # - mac=<dataname> Pull the value from a data plugin with the key dataname
    result = dict()
    entries = node['autointerfaces'].split(';')
    for entry in entries:
        components = entry.split(',')
        iface = components[0]
        result[iface] = dict()
        result[iface]['network'] = components[1]
        result[iface]['ip'] = Network.ipadd(components[1], node['nodeindex'] + int(components[2]))
        for i in range(3, len(components)):
            entities = components[i].split("=", 1)
            if entities[0] == "mac":
                result[iface]['mac'] = lambda key=entities[1],name=node['name']: Node.data(key, name)
            else:
                if '+' in entities[1]:
                    result[iface][entities[0]] = entities[1].split('+')
                else:
                    result[iface][entities[0]] = entities[1]
    node.setrawitem('interfaces', result)
    del node['autointerfaces']
