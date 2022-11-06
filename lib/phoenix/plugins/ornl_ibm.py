#!/usr/bin/env python3
"""Custom Plugin for the IBM machines at ORNL"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import re

name_regex = re.compile(r'(.)(\d{2})n(\d{2})')

columns=36
nodespercol=18

def set_node_attrs(node, alias=None):
    logging.debug("Running ornl_ibm plugin for node %s" % (node['name']))

    # Extract node index number from the name
    m = name_regex.search(node['name'])
    if m is not None:
        node['row'] = m.group(1)
        node['rownum'] = ord(node['row']) - 97
        node['column'] = int(m.group(2))
        node['rack'] = "%s%02d" % (m.group(1), int(m.group(2)))
        node['nodepos'] = int(m.group(3))

        # Calculate the node index
        node['nodeindex'] = (((node['rownum'] * columns) + (node['column'] - 1)) * nodespercol) + (node['nodepos'] - 1)

        #node['nodeindex'] = int(m[-1])
        #node['nodenums'] = [ int(x) for x in m ]
