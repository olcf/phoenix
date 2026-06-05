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
            if 'interfaces' not in node:
                raise KeyError("Node '%s' has no 'interfaces' defined" % node['name'])
            if interface not in node['interfaces']:
                raise KeyError("Node '%s' has no interface '%s' defined" % (node['name'], interface))
            iface = node['interfaces'][interface]
            if 'ip' not in iface:
                raise KeyError("Node '%s' interface '%s' is missing 'ip'" % (node['name'], interface))
            ip = iface['ip']
            if 'network' not in iface:
                raise KeyError("Node '%s' interface '%s' is missing 'network' (should reference a network defined in networks.yaml)" % (node['name'], interface))
            networkname = iface['network']
            networks = Network.networks()
            if networkname not in networks:
                raise KeyError("Node '%s' interface '%s' references network '%s' which is not defined in networks.yaml" % (node['name'], interface, networkname))
            network = networks[networkname]
            if 'netmask' not in network:
                raise KeyError("Network '%s' (used by node '%s' interface '%s') is missing 'netmask' in networks.yaml" % (networkname, node['name'], interface))
            gateway = network.get('gateway', '')
            netmask = network['netmask']
            ifacename = iface['interfacename'] if 'interfacename' in iface else interface
            ipline = "%s::%s:%s:${hostname}:%s:none" % (ip, gateway, netmask, ifacename)
        else:
            ipline = None

        if 'ipxe_template' in node:
            try:
                template = Node.environment.get_template(node['ipxe_template'])
            except:
                logging.error("Could not generate an ipxe file for node '%s' - Template '%s' was not found" % (node['name'], node['ipxe_template']))
                raise
        else:
            template = cls.def_template
        script = template.render({'node': node, 'ipline': ipline})
        return script
