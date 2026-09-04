#!/usr/bin/env python3
"""Phoenix bootloader support for iPXE"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import re
from phoenix.bootloader import Bootloader, BootloaderConfigError
from phoenix.node import Node
from phoenix.network import Network

class IpxeBootloader(Bootloader):
    bootloadertype = 'ipxe'
    def_template = Node.environment.get_template('ipxe.j2')
    def_bondoptions = 'mode=802.3ad,miimon=100'

    # dracut recovers the vlan id by parsing the device name, so the name must
    # be one of the four styles it knows about. See dracut.cmdline(7):
    # VLAN_PLUS_VID (vlan0005), VLAN_PLUS_VID_NO_PAD (vlan5),
    # DEV_PLUS_VID (eth0.0005), DEV_PLUS_VID_NO_PAD (eth0.5)
    re_vlanname = re.compile(r'^(?:vlan|([^.]+)\.)(\d{1,4})$')

    @classmethod
    def script(cls, node, interface=None):
        logging.debug("Generating iPXE script for node %s", node['name'])

        if 'image' not in node:
            raise KeyError('No image set for %s, not generating bootfile' % node['name'])

        netargs = cls._netargs(node, bootinterface=interface)

        if 'ipxe_template' in node:
            try:
                template = Node.environment.get_template(node['ipxe_template'])
            except:
                logging.error("Could not generate an ipxe file for node '%s' - Template '%s' was not found", node['name'], node['ipxe_template'])
                raise
        else:
            template = cls.def_template
        script = template.render({'node': node,
                                  'netargs': ' '.join(netargs)})
        return script

    @classmethod
    def _netargs(cls, node, bootinterface=None):
        """Build the dracut network arguments for a node.

           'bootinterface' is the interface this bootfile is being generated
           for. It is configured with an ip= argument, as is any other
           interface marked 'neednet', along with the bond= and vlan=
           arguments needed to construct the devices they name. The boot
           interface becomes the dracut bootdev=.

           With no 'bootinterface' the node is left to DHCP on whichever
           interface iPXE booted from, since nothing identifies which one that
           was.
        """
        # Nothing to configure statically, so let dracut DHCP on whichever
        # interface iPXE booted from.
        if bootinterface is None:
            return ['BOOTIF=${mac}', 'ip=dhcp']

        interfaces = node['interfaces'] if 'interfaces' in node else {}
        if not interfaces:
            raise BootloaderConfigError("Node '%s' has no 'interfaces' defined" % node['name'])
        if bootinterface not in interfaces:
            raise BootloaderConfigError("Node '%s' has no interface '%s' defined" % (node['name'], bootinterface))

        # Netdev arguments construct the interfaces that ip= then refers to, so
        # they are emitted first, bonds ahead of the vlans built on them. Both
        # are keyed by device name so that a bond serving as a vlan parent is
        # only emitted once.
        bondargs = dict()
        vlanargs = dict()
        ipargs = []
        bootdev = None

        networks = Network.networks()
        # Map device name back to its config so that vlanparent can reference
        # either the interface key or its interfacename.
        devices = {cls._devicename(key, iface): (key, iface)
                   for key, iface in interfaces.items()}

        # Sorted so that a node's bootfiles are reproducible; the merged
        # interface mapping does not preserve the order they were written in.
        for interface, iface in sorted(interfaces.items()):
            if interface != bootinterface:
                # Only the interface being booted from is configured unless
                # another is explicitly marked as needed in the initramfs.
                if interface == 'bmc':
                    continue
                if 'neednet' not in iface or not iface['neednet']:
                    continue

            devicename = cls._devicename(interface, iface)
            network = cls._network(node, interface, iface, networks)
            # A dual stack interface gets one ip= per family.
            ifacelines = cls._iplines(node, interface, iface, devicename, network)

            # A device named in one of dracut's vlan styles is a vlan whether
            # or not vlanparent was set, since dracut will parse a vlan id out
            # of the name regardless.
            isvlan = 'vlanparent' in iface or cls._parsevlanname(devicename)[1] is not None
            if 'bondmembers' in iface and isvlan:
                raise BootloaderConfigError("Node '%s' interface '%s' cannot be both a bond and a vlan; describe the bond as its own interface and point 'vlanparent' at it" % (node['name'], interface))

            if 'bondmembers' in iface:
                # The MTU belongs on the bond itself, so _bondline puts it in
                # the 4th field of bond= rather than the 8th field of ip=.
                bondargs[devicename] = cls._bondline(node, interface, iface, devicename, network)
            else:
                if isvlan:
                    parent = cls._vlanparent(node, interface, iface, devicename)
                    vlanargs[devicename] = "vlan=%s:%s" % (devicename, parent)
                    # A vlan sits on a parent that may itself need constructing
                    # and that carries no address of its own.
                    cls._addbondparent(node, parent, devices, networks, bondargs)
                if 'mtu' in network:
                    ifacelines = ["%s:%s" % (line, network['mtu']) for line in ifacelines]

            ipargs.extend("ip=%s" % line for line in ifacelines)
            if interface == bootinterface:
                bootdev = devicename

        netdevargs = list(bondargs.values()) + list(vlanargs.values())
        if not netdevargs and len(ipargs) == 1:
            # BOOTIF names the single NIC that PXE booted from, and generates
            # the hook that waits for it to finish coming up before the root
            # filesystem is fetched.
            return ['BOOTIF=${mac}'] + ipargs

        # When the address lives on a bond or vlan, BOOTIF would have dracut
        # configure the underlying member instead, so it is left off entirely
        # rather than suppressed afterwards with rd.bootif=0. bootdev= takes
        # over naming the interface to wait for and route through, and dracut
        # requires it whenever there is more than one ip= anyway.
        return netdevargs + ipargs + ["bootdev=%s" % bootdev]

    @classmethod
    def _devicename(cls, interface, iface):
        """The name of an interface as the booted kernel will see it"""
        return iface['interfacename'] if 'interfacename' in iface else interface

    @classmethod
    def _iplines(cls, node, interface, iface, devicename, network):
        """Build the values of the dracut ip= arguments for an interface. See
           dracut.cmdline(7):
           ip=<client-IP>:[<peer>]:<gateway-IP>:<netmask>:<hostname>:<device>:none

           A dual stack interface produces one line per family, which dracut's
           network-manager and systemd-networkd modules merge onto the single
           device. IPv6 addresses are bracketed so that their colons are not
           read as field separators.
        """
        iplines = []

        if 'ip' in iface:
            if 'netmask' not in network:
                raise BootloaderConfigError("Network '%s' (used by node '%s' interface '%s') is missing 'netmask' in networks.yaml" % (iface['network'], node['name'], interface))
            iplines.append("%s::%s:%s:${hostname}:%s:none" % (iface['ip'],
                                                              network.get('gateway', ''),
                                                              network['netmask'],
                                                              devicename))

        if 'ip6' in iface:
            # The prefix length is used rather than netmask6, which dracut's
            # ipv6 handling does not accept.
            if 'prefix6' not in network:
                raise BootloaderConfigError("Network '%s' (used by node '%s' interface '%s') is missing an ipv6 prefix in networks.yaml" % (iface['network'], node['name'], interface))
            iplines.append("%s::%s:%s:${hostname}:%s:none" % (cls._bracket(iface['ip6']),
                                                              cls._bracket(network.get('gateway6', '')),
                                                              network['prefix6'],
                                                              devicename))

        if not iplines:
            raise BootloaderConfigError("Node '%s' interface '%s' is missing 'ip' (or 'ip6')" % (node['name'], interface))

        return iplines

    @classmethod
    def _bracket(cls, address):
        """Bracket an ipv6 address so dracut does not read its colons as the
           field separators of ip=
        """
        address = str(address)
        if ':' not in address or address.startswith('['):
            return address
        return "[%s]" % address

    @classmethod
    def _network(cls, node, interface, iface, networks):
        """Look up the network an interface references"""
        if 'network' not in iface:
            raise BootloaderConfigError("Node '%s' interface '%s' is missing 'network' (should reference a network defined in networks.yaml)" % (node['name'], interface))
        networkname = iface['network']
        if networkname not in networks:
            raise BootloaderConfigError("Node '%s' interface '%s' references network '%s' which is not defined in networks.yaml" % (node['name'], interface, networkname))
        return networks[networkname]

    @classmethod
    def _addbondparent(cls, node, parent, devices, networks, bondargs):
        """Add the bond= argument for a vlan's parent when that parent is a
           bond this node describes. A parent that is a physical NIC needs no
           argument of its own.
        """
        if parent in bondargs or parent not in devices:
            return
        interface, iface = devices[parent]
        if 'bondmembers' not in iface:
            return
        # The parent carries no address of its own, so its network is only
        # consulted for an MTU.
        network = networks.get(iface['network'], {}) if 'network' in iface else {}
        bondargs[parent] = cls._bondline(node, interface, iface, parent, network)

    @classmethod
    def _bondline(cls, node, interface, iface, devicename, network):
        """Build the dracut bond= argument for an interface. See
           dracut.cmdline(7): bond=<bondname>:<bondmembers>:<options>:<mtu>
        """
        bondmembers = iface['bondmembers']
        if isinstance(bondmembers, str):
            bondmembers = bondmembers.split(',')
        members = [str(m).strip() for m in bondmembers if str(m).strip() != '']
        if not members:
            raise BootloaderConfigError("Node '%s' interface '%s' has an empty 'bondmembers'" % (node['name'], interface))
        for member in members:
            if ':' in member:
                raise BootloaderConfigError("Node '%s' interface '%s' bondmember '%s' must not contain ':'" % (node['name'], interface, member))
        if devicename in members:
            raise BootloaderConfigError("Node '%s' interface '%s' lists the bond itself '%s' in its own 'bondmembers'" % (node['name'], interface, devicename))

        # An empty options field leaves a trailing colon that some dracut
        # network modules treat as a hard error, so fall back to the default.
        bondoptions = str(iface['bondoptions']).strip() if 'bondoptions' in iface else ''
        if bondoptions == '':
            bondoptions = cls.def_bondoptions
        if ':' in bondoptions:
            raise BootloaderConfigError("Node '%s' interface '%s' 'bondoptions' must not contain ':' (use ';' to separate multi-valued options such as arp_ip_target)" % (node['name'], interface))

        bondline = "bond=%s:%s:%s" % (devicename, ','.join(members), bondoptions)

        # The MTU applies to the bond, so it goes here rather than on ip=.
        if 'mtu' in network:
            bondline = "%s:%s" % (bondline, network['mtu'])

        return bondline

    @classmethod
    def _vlanparent(cls, node, interface, iface, devicename):
        """Validate a vlan interface and return the parent device to build it
           on. The vlan id is not passed to dracut separately, it is parsed out
           of the device name, so the name must encode the intended vlan in one
           of the styles dracut recognizes.
        """
        namedparent, vlanid = cls._parsevlanname(devicename)
        if vlanid is None:
            raise BootloaderConfigError("Node '%s' interface '%s' device name '%s' does not encode a vlan id in a style dracut supports (vlan5, vlan0005, eth0.5 or eth0.0005)" % (node['name'], interface, devicename))

        parent = str(iface['vlanparent']).strip() if 'vlanparent' in iface else ''
        if parent == '':
            # DEV_PLUS_VID names the parent, so vlanparent only has to be set
            # explicitly for the VLAN_PLUS_VID styles.
            parent = namedparent
        if not parent:
            raise BootloaderConfigError("Node '%s' interface '%s' device name '%s' does not name a parent device, so 'vlanparent' must be set" % (node['name'], interface, devicename))
        if ':' in parent:
            raise BootloaderConfigError("Node '%s' interface '%s' 'vlanparent' '%s' must not contain ':'" % (node['name'], interface, parent))
        if namedparent is not None and namedparent != parent:
            raise BootloaderConfigError("Node '%s' interface '%s' device name '%s' is built on '%s' but 'vlanparent' is '%s'" % (node['name'], interface, devicename, namedparent, parent))

        return parent

    @classmethod
    def _parsevlanname(cls, devicename):
        """Parse a vlan device name into a (parent, vlanid) tuple. The parent
           is None for the VLAN_PLUS_VID styles, which do not encode one. The
           vlan id is None if the name is not a style dracut recognizes.
        """
        match = cls.re_vlanname.match(devicename)
        if not match:
            return (None, None)
        parent, digits = match.groups()
        # VLAN_PLUS_VID and DEV_PLUS_VID pad the id to four digits, the NO_PAD
        # variants do not pad at all. Anything in between is not a dracut style.
        vlanid = int(digits)
        if digits not in ('%d' % vlanid, '%04d' % vlanid):
            return (None, None)
        return (parent, vlanid)
