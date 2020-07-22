#!/usr/bin/env python
"""Phoenix system management"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import os
import logging

from ClusterShell.NodeUtils import GroupResolver
from ClusterShell.NodeSet import set_std_group_resolver
from Phoenix.System import PhoenixGroupSource


def setup_logging(level=0):
    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(len(levels)-1,level)]
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

# Lightweight attempt to standardize a location for config files
try:
    conf_path = os.environ['PHOENIX_CONF']
except KeyError:
    conf_path = '/etc/phoenix'


try:
    data_pata = os.environ['PHOENIX_DATA']
except KeyError:
    data_path = '/var/opt/phoenix/data'

try:
    artifact_path = os.environ['PHOENIX_ARTIFACTS']
except KeyError:
    artifact_path = '/srv/www/htdocs/phoenix'

groupsource = PhoenixGroupSource()
set_std_group_resolver(GroupResolver(groupsource))
