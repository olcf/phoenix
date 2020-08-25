#!/usr/bin/env python
"""Phoenix system management"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import os
import logging
import sys

from ClusterShell.NodeUtils import GroupResolver
from ClusterShell.NodeSet import set_std_group_resolver
from phoenix.system import System
from phoenix.group import PhoenixGroupSource


def setup_logging(level=0):
    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(len(levels)-1,level)]
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

#default_providers = { 'dhcp'      : 'dnsmasq',
#                      'bootloader': 'ipxe'
#                    }

def get_component(category, provider=None, providerclass=None):
    packagefile = "phoenix." + category
    if packagefile not in list(sys.modules):
        logging.debug("Loading package %s", packagefile)
        __import__(packagefile)

    if provider is None:
	System.load_config()
	try:
	    provider = System.config[category]
	except KeyError:
	    provider = getattr(sys.modules[packagefile], 'DEFAULT_PROVIDER')
    provider = provider.lower()

    modulefile = provider
    modname = "phoenix.%s.%s" % (category, modulefile)

    # Check if the module needs to be loaded, load it if required
    if modname not in list(sys.modules):
        logging.debug("Loading module %s", modname)
        # Import module if not yet loaded
        __import__(modname)

    # Get the class pointer
    if providerclass == None:
        providerclass = provider.capitalize() + category.capitalize()
    try:
        return getattr(sys.modules[modname], providerclass)
    except:
        raise ImportError("Could not find class %s" % providerclass)

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
