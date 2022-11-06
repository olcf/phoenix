#!/usr/bin/env python3
"""DHCP support"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import phoenix
from phoenix.system import System

class Dhcp(object):
    dhcptype = "unknown"

    @classmethod
    def update_dhcp_reservations(cls):
        raise NotImplementedError

    @classmethod
    def get_dhcp_conf():
        raise NotImplementedError

def load_dhcp_provider():
    return phoenix.get_component('dhcp')

DEFAULT_PROVIDER='dnsmasq'
