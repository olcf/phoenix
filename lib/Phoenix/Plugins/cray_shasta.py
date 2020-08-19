#!/usr/bin/env python
"""Plugin for Cray shasta machines"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import re

shasta_regex = re.compile(r'x(?P<racknum>\d+)[ce](?P<chassis>\d+)([rs](?P<slot>\d+)(b(?P<board>\d+)(n(?P<nodenum>\d+))?)?)?')
ipprefix = 'fc00:0:100:60'

# colorado_map[slot][node]
colorado_map = {
    0: { 0: 51, 1: 50 },
    1: { 0: 35, 1: 34 },
    2: { 0: 49, 1: 48 },
    3: { 0: 33, 1: 32 },
    4: { 0: 16, 1: 17 },
    5: { 0: 0,  1: 1  },
    6: { 0: 18, 1: 19 },
    7: { 0: 2,  1: 3  }
}

def set_node_attrs(node):
    ''' Sets attributes for nodes in the system
        Note that a "node" in this context could be a
        compute node, nC, cC, cec, or switch
    '''
    logging.debug("Running cray_shasta plugin for node %s", node['name'])

    m = shasta_regex.search(node['name'])

    if m is None:
        logging.debug("Name '%s' did not match the regex", node['name'])
        return

    try:
        node['rack'] = 'x%s' % m.group('racknum')
        node['racknum'] = int(m.group('racknum'))
        node['chassis'] = int(m.group('chassis'))
        node['slot'] = int(m.group('slot'))
        node['board'] = int(m.group('board'))
        node['nodenum'] = int(m.group('nodenum'))
    except TypeError:
        # If the name didn't contain the match, it will return None
        # Converting it to an int will return a TypeError which we just ignore
        pass

    if node['type'] == 'compute':
        node['redfishpath'] = 'Systems/Node%d' % node['nodenum']
        node['firmware_name'] = 'Node%d.BIOS' % node['nodenum']
        node['firmware_target'] = '/redfish/v1/UpdateService/FirmwareInventory/Node%d.BIOS' % node['nodenum']
        node['bmctype'] = 'redfish'
        node['bmc'] = "x{racknum}c{chassis}s{slot}b{board}".format(**node.attr)
        node['bmcuser'] = 'root'
        node['bmcpassword'] = 'initial0'
        # XXX This is a poor assumption, make configurable
        node['hsngroup'] = (node['racknum'] % 1000) + 1
        node['hsnswitch'] = _hsnswitchname(node['racknum'], node['chassis'], node['board'])
        node['hsnmac'] = _hsnalgomac(node['hsngroup'], _hsnswitchnum(node['chassis'], node['board']), colorado_map[node['slot']][node['nodenum']])

    elif node['type'] == 'nc':
        node['redfishpath'] = 'Chassis/Blade%d' % node['slot']
        node['firmware_name'] = 'BMC'
        node['bmctype'] = 'redfish'
        node['bmc'] = "x{racknum}c{chassis}s{slot}b{board}".format(**node.attr)
        node['bmcuser'] = 'root'
        node['bmcpassword'] = 'initial0'
        node['pdu'] = "x{racknum}c{chassis}".format(**node.attr)
        node['pdutype'] = 'redfish'
        node['pduuser'] = 'root'
        node['pdupassword'] = 'initial0'
        _setinterfaceparam(node, 'me0', 'mac', _mgmtalgomac(node['racknum'], node['chassis'], node['slot'] + 48, node['board']))
        _setinterfaceparam(node, 'me0', 'dhcp', True)
        _setinterfaceparam(node, 'me0', 'hostname', node['name'])
        _setinterfaceparam(node, 'me0', 'ip6', _mgmtalgoipv6addr(node['racknum'], node['chassis'], node['slot'] + 48, node['board']))

    elif node['type'] == 'blade':
        node['redfishpath'] = 'Chassis/Blade%d' % node['slot']
        node['bmctype'] = 'redfish'
        node['bmc'] = "x{racknum}c{chassis}".format(**node.attr)
        node['bmcuser'] = 'root'
        node['bmcpassword'] = 'initial0'

    elif node['type'] == 'cc':
        node['redfishpath'] = 'Chassis/Enclosure'
        node['firmware_name'] = 'BMC'
        node['bmctype'] = 'redfish'
        node['bmc'] = node['name']
        node['bmcuser'] = 'root'
        node['bmcpassword'] = 'initial0'
        _setinterfaceparam(node, 'me0', 'mac', _mgmtalgomac(node['racknum'], node['chassis'], 0, 0))
        _setinterfaceparam(node, 'me0', 'dhcp', True)
        _setinterfaceparam(node, 'me0', 'hostname', node['name'])
        _setinterfaceparam(node, 'me0', 'ip6', _mgmtalgoipv6addr(node['racknum'], node['chassis'], 0, 0))

    elif node['type'] == 'switch':
        node['switchtype'] = 'slingshot'
        if 'switchmodel' not in node:
            racknum = node['racknum']
            # This is based on 2020 product availability and naming convention
            if (racknum >= 1000 and racknum < 3000) or racknum >= 9000:
                node['switchmodel'] = 'colorado'
            else:
                node['switchmodel'] = 'columbia'
        node['redfishpath'] = 'Chassis/Enclosure'
        node['bmctype'] = 'redfish'
        node['bmc'] = node['name'] # Technically this is a switch controller
        node['bmcuser'] = 'root'
        node['bmcpassword'] = 'initial0'
        if node['switchmodel'] is 'colorado':
            node['pdutype'] = 'redfish'
            node['pdu'] = "x{racknum}c{chassis}".format(**node.attr)
            node['pduuser'] = 'root'
            node['pdupassword'] = 'initial0'
            node['pduredfishpath'] = 'Chassis/Perif%d' % node['slot']
            _setinterfaceparam(node, 'eth0', 'dhcp', True)
            _setinterfaceparam(node, 'eth0', 'mac', _mgmtalgomac(node['racknum'], node['chassis'], node['slot'] + 96, 0))
            _setinterfaceparam(node, 'eth0', 'ip6', _mgmtalgoipv6addr(node['racknum'], node['chassis'], node['slot'] + 96, 0))
            _setinterfaceparam(node, 'me0', 'hostname', node['name'])
        node['firmware_name'] = 'BMC'

    elif node['type'] == 'cec':
        node['ip6'] = "%s:0:a%d:%x:0" % (ipprefix, node['chassis'], node['racknum'])
        # The CECs live in a chassis, but remove this for now
        del node['chassis']

def _setinterfaceparam(node, interface, paramname, paramvalue):
    """ Updates a node's interface with a certain value """
    if 'interfaces' not in node:
        node['interfaces'] = dict()
    if interface not in node['interfaces']:
        node['interfaces'][interface] = dict()
    if paramname in node['interfaces'][interface]:
        # User already set this, don't overwrite
        return
    node['interfaces'][interface][paramname] = paramvalue

def _mgmtalgomac(rack, chassis, slot, idx, prefix=2):
    """ Returns the string representation of an algorithmic mac address """
    return "%02x:%02x:%02x:%02x:%02x:%02x" % (prefix, rack >> 8, rack & 0xFF, chassis, slot, idx << 4)

def _mgmtalgoipv6addr(rack, chassis, slot, idx, prefix='fc00:0:100:60'):
    """ Returns the EUI64 IP as a string """
    return "%s:%02x:%02xff:fe%02x:%02x%02x" % (prefix, rack >> 8, rack & 0xFF, chassis, slot, idx << 4)

def _hsnalgomac(group, switch, port):
    """ Returns the string representation of an algorithmic mac address """
    # A mac address is 48 bits
    # [ padding ][ group  ][ switch ][  port  ]
    # [ 28 bits ][ 9 bits ][ 5 bits ][ 6 bits ]
    # Bit 41 (in the padding) must be set to indicate "locally assigned"
    mac = (1 << 41) + (group << 11) + (switch << 6) + port
    macstr = "%012x" % mac
    return "%s:%s:%s:%s:%s:%s" % (macstr[0:2], macstr[2:4], macstr[4:6], macstr[6:8], macstr[8:10], macstr[10:12])

def _hsnswitchname(rack, chassis, board):
    """ Determines the name of the HSN switch """
    # XXX review with a full Olympus
    if board == 0:
        whichswitchslot = 3
    elif board == 1:
        whichswitchslot = 7
    return "x%dc%dr%db0" % (rack, chassis, whichswitchslot)

def _hsnswitchnum(chassis, board, type='hill'):
    """ Given the cabinet type, chassis number, and board number,
        return the (local) switch number
    """
    # XXX Update with a full Olympus
    if type == 'hill':
        switchnum = board
        if chassis == 3:
            switchnum = switchnum + 2
        return switchnum
    return 0

if __name__ == '__main__':
    print _hsnalgomac(1, 1, 47)
    print _hsnalgomac(1, 1, colorado_map[0][0])
