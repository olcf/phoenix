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
    def_bondoptions = 'mode=802.3ad,miimon=100'

    @classmethod
    def script(cls, node, interface=None):
        logging.debug("Generating iPXE script for node %s", node['name'])

        if 'image' not in node:
            raise KeyError('No image set for %s, not generating bootfile' % node['name'])

        interfaces = [interface] if interface else []
        netargs, iplines = cls._netargs(node, interfaces)

        if 'ipxe_template' in node:
            try:
                template = Node.environment.get_template(node['ipxe_template'])
            except:
                logging.error("Could not generate an ipxe file for node '%s' - Template '%s' was not found", node['name'], node['ipxe_template'])
                raise
        else:
            template = cls.def_template
        script = template.render({'node': node,
                                  'netargs': ' '.join(netargs),
                                  'ipline': iplines[0] if iplines else None})
        return script

    @classmethod
    def _netargs(cls, node, interfaces):
        """Build the dracut network arguments for the given interfaces.
           Returns a (arguments, iplines) tuple, where iplines holds the value
           of each ip= argument for the benefit of custom templates.
        """
        # Netdev arguments (bond=, and eventually vlan=) construct interfaces
        # that ip= then refers to, so they are emitted first.
        netdevargs = []
        ipargs = []
        iplines = []
        bootdev = None
        bonded = False

        networks = Network.networks()
        for interface in interfaces:
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
            if networkname not in networks:
                raise KeyError("Node '%s' interface '%s' references network '%s' which is not defined in networks.yaml" % (node['name'], interface, networkname))
            network = networks[networkname]
            if 'netmask' not in network:
                raise KeyError("Network '%s' (used by node '%s' interface '%s') is missing 'netmask' in networks.yaml" % (networkname, node['name'], interface))
            gateway = network.get('gateway', '')
            netmask = network['netmask']
            ifacename = iface['interfacename'] if 'interfacename' in iface else interface

            ipline = "%s::%s:%s:${hostname}:%s:none" % (ip, gateway, netmask, ifacename)
            bondline = cls._bondline(node, interface, iface, ifacename, network)
            if bondline is not None:
                netdevargs.append(bondline)
                bonded = True
            elif 'mtu' in network:
                # Without a bond the MTU goes in the 8th field of ip=. With a
                # bond it belongs on the bond itself via the 4th field of bond=.
                ipline = "%s:%s" % (ipline, network['mtu'])

            iplines.append(ipline)
            ipargs.append("ip=%s" % ipline)
            # An interface marked primary becomes the bootdev, otherwise the
            # first one configured wins.
            if bootdev is None or ('primary' in iface and iface['primary']):
                bootdev = ifacename

        if not ipargs:
            # Nothing to configure statically, so let dracut DHCP on whichever
            # interface iPXE booted from.
            return (['BOOTIF=${mac}', 'ip=dhcp'], iplines)

        args = []
        if not bonded:
            # BOOTIF names the single NIC that PXE booted from. When that NIC
            # belongs to a bond, dracut would configure the member instead of
            # the bond, so it is left off entirely rather than suppressed
            # afterwards with rd.bootif=0.
            args.append('BOOTIF=${mac}')
        args.extend(netdevargs)
        args.extend(ipargs)
        if bonded or len(ipargs) > 1:
            # Required by dracut for multiple ip= arguments. It also generates
            # the hook that waits for the interface to finish coming up before
            # the root filesystem is fetched, which BOOTIF would otherwise do.
            args.append("bootdev=%s" % bootdev)
        return (args, iplines)

    @classmethod
    def _bondline(cls, node, interface, iface, ifacename, network):
        """Build the dracut bond= argument for an interface, or None if it is
           not a bond. See dracut.cmdline(7):
           bond=<bondname>:<bondmembers>:<options>:<mtu>
        """
        if 'bondmembers' not in iface:
            return None

        bondmembers = iface['bondmembers']
        if isinstance(bondmembers, str):
            bondmembers = [m.strip() for m in bondmembers.split(',')]
        members = [str(m).strip() for m in bondmembers if str(m).strip() != '']
        if not members:
            raise ValueError("Node '%s' interface '%s' has an empty 'bondmembers'" % (node['name'], interface))
        for member in members:
            if ':' in member:
                raise ValueError("Node '%s' interface '%s' bondmember '%s' must not contain ':'" % (node['name'], interface, member))
        if ifacename in members:
            raise ValueError("Node '%s' interface '%s' lists the bond itself '%s' in its own 'bondmembers'" % (node['name'], interface, ifacename))

        # An empty options field leaves a trailing colon that some dracut
        # network modules treat as a hard error, so fall back to the default.
        bondoptions = str(iface['bondoptions']).strip() if 'bondoptions' in iface else ''
        if bondoptions == '':
            bondoptions = cls.def_bondoptions
        if ':' in bondoptions:
            raise ValueError("Node '%s' interface '%s' 'bondoptions' must not contain ':' (use ';' to separate multi-valued options such as arp_ip_target)" % (node['name'], interface))

        bondline = "bond=%s:%s:%s" % (ifacename, ','.join(members), bondoptions)

        # The MTU applies to the bond, so it goes here rather than on ip=.
        if 'mtu' in network:
            bondline = "%s:%s" % (bondline, network['mtu'])

        return bondline
