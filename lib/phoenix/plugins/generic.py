#!/usr/bin/env python
"""Generic Plugin run on systems/nodes without an explicit plugin defined"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import re
from phoenix.system import System
from phoenix.network import Network
from phoenix.network import handleautointerfaces

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
