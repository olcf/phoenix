#!/usr/bin/env python3
"""Phoenix bootloader support for iPXE"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
from phoenix.bootloader import Bootloader
from phoenix.node import Node
from phoenix.network import Network

class IpxeBootloader(Bootloader):
    bootloadertype = 'ipxe'
    def_template = Node.environment.get_template('ipxe.j2')

    @classmethod
    def script(cls, node, interface=None):
        logging.debug("Generating iPXE script for node %s", node['name'])

        if 'image' not in node:
            raise KeyError('No image set for %s, not generating bootfile' % node['name'])

        if interface:
            iface = node['interfaces'][interface]
            ip = iface['ip']
            networks = Network.networks()
            networkname = iface['network']
            gateway = networks[networkname]['gateway']
            netmask = networks[networkname]['netmask']
            ifacename = iface['interfacename'] if 'interfacename' in iface else interface
            ipline = "%s::%s:%s:${hostname}:%s:none" % (ip, gateway, netmask, ifacename)
        else:
            ipline = None

        script = cls.def_template.render({'node': node, 'ipline': ipline})
        return script
