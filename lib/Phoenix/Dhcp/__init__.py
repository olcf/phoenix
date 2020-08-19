#!/usr/bin/env python
"""DHCP support"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import Phoenix
from Phoenix.System import System

class Dhcp(object):
    dhcptype = "unknown"

    @classmethod
    def update_dhcp_reservations(cls):
        raise NotImplementedError

    @classmethod
    def get_dhcp_conf():
        raise NotImplementedError

def load_dhcp_provider():
    System.load_config()
    try:
        prog = System.config['dhcp']
    except KeyError:
        prog = 'dnsmasq'

    classname = prog.lower().capitalize()
    modname = "Phoenix.Dhcp.%s" % classname

    # Iterate over a copy of sys.modules' keys to avoid RuntimeError
    if modname.lower() not in [mod.lower() for mod in list(sys.modules)]:
        # Import module if not yet loaded
        __import__(modname)

    # Get the class pointer
    try:
        return getattr(sys.modules[modname], 'Dhcp' + classname)
    except:
        raise ImportError("Could not find class %s" % classname)

