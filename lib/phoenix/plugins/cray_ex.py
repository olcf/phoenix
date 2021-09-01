#!/usr/bin/env python
"""Plugin for HPE Cray EX machines"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import re
from ClusterShell.NodeSet import NodeSet
from phoenix.system import System

cray_ex_regex = re.compile(r'x(?P<racknum>\d+)[ce](?P<chassis>\d+)((?P<slottype>[rs])(?P<slot>\d+)(b(?P<board>\d+)(n(?P<nodenum>\d+))?)?)?')
num_regex = re.compile(r'.*?(\d+)$')
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

# These are defaults for the cray_ex plugin
settings = {
    'startnid':     1,
    'niddigits':    5,
    'nodesperrack': 256,
}


try:
    usersettings = System.setting('cray_ex')
    settings.update(usersettings)
except:
    logging.error("cray_shasta section not found in system settings")
if 'racks' in settings:
    settings['racknodeset'] = NodeSet(settings['racks'])
    settings['racklist'] = list(settings['racknodeset'])
else:
    logging.error("racks not set in system.yaml cray_shasta section")

def _xname_to_node_attrs(node):
    global settings
    m = cray_ex_regex.search(node['xname'])

    if m is None:
        logging.debug("Name '%s' (%s) did not match the regex", node['name'], node['xname'])
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

    if 'type' not in node:
        if 'nodenum' in node:
            node['type'] = 'compute'
        elif 'board' in node:
            node['type'] = 'nc'
        elif 'slot' in node:
            slottype = m.group('slottype')
            if slottype == 'r':
                node['type'] = 'switch'
            else:
                node['type'] = 'blade'
        elif 'chassis' in node:
            node['type'] = 'cc'

    node['rackidx'] = settings['racklist'].index(node['rack'])

def _nid_to_node_attrs(node):
    ''' If a node has nodeindex set, try to figure out the xname details'''
    global settings
    logging.debug("Inside _nid_to_node_attrs for node %s", node['name'])

    if 'nodeindex' not in node:
        logging.debug("nodeindex not set for node %s", node['name'])
        return

    if 'type' not in node:
        node['type'] = 'compute'

    # FIXME: Make this configurable (support Hill)
    nodesperchassis = settings['nodesperrack']//8
    nodesperslot = nodesperchassis//8
    nodesperboard = nodesperslot//2

    nid = node['nodeindex']
    # Python has divmod(), but for small numbers it's actually slower due to function call overhead
    rackidx=(nid-settings['startnid'])//settings['nodesperrack']
    rackoffset=(nid-settings['startnid'])%settings['nodesperrack']
    chassisidx=rackoffset//nodesperchassis
    chassisoffset=rackoffset%nodesperchassis
    slotidx=chassisoffset//nodesperslot
    slotoffset=chassisoffset%nodesperslot
    boardidx=slotoffset//nodesperboard
    boardoffset=slotoffset%nodesperboard
    nodeidx=boardoffset

    node['nodeindexinrack'] = rackoffset
    node['rack']    = settings['racklist'][rackidx]
    node['rackidx'] = rackidx
    node['racknum'] = int(node['rack'][1:])
    node['chassis'] = chassisidx
    node['slot']    = slotidx
    node['board']   = boardidx
    node['nodenum'] = nodeidx
    node['xname']   = "%sc%ds%db%dn%d"%(node['rack'], chassisidx, slotidx,
                                        boardidx, nodeidx)

def set_node_attrs(node, alias=None):
    ''' Sets attributes for nodes in the system
        Note that a "node" in this context could be a
        compute node, nC, cC, cec, or switch
    '''
    logging.debug("Running cray_ex plugin for node %s", node['name'])

    global settings

    # FIXME: This won't do the right thing if you system name starts with 'x'
    #        Hopefully that won't bite us any time soon...
    #        Could instead have a lightweight regex, but that might hurt
    #        performance too much
    if node['name'].startswith('x'):
        logging.debug("Node name %s is an xname", node['name'])
        node['xname'] = node['name']
        _xname_to_node_attrs(node)
        if 'rack' not in node:
            logging.error("Could not parse xname")
            return
    else:
        logging.debug("Node name %s is NOT an xname", node['name'])
        m = num_regex.match(node['name'])
        if m is not None:
            node['nodeindex'] = int(m.group(1))
            _nid_to_node_attrs(node)
            logging.debug("test8")
        logging.debug("test9")
        if 'xname' not in node and alias is not None and alias.startswith('x'):
            node['xname'] = alias
        logging.debug("test10")
        if 'xname' not in node:
            logging.error("Cray EX component %s does not have an xname", node['name'])
            return
        logging.debug("test11")

    # This needs to eventually move to models instead of polluting every node
    node['redfishsimpleupdate'] = 'UpdateService/Actions/SimpleUpdate'

    if node['type'] == 'compute':
        node['redfishpath'] = 'Systems/Node%d' % node['nodenum']
        node['firmware_name'] = 'Node%d.BIOS' % node['nodenum']
        node['firmware_target'] = '/redfish/v1/UpdateService/FirmwareInventory/Node%d.BIOS' % node['nodenum']
        node['bmctype'] = 'redfish'
        node['bmc'] = "x{racknum}c{chassis}s{slot}b{board}".format(**node.attr)
        node['bmcuser'] = 'root'
        node['discoverytype'] = 'bmc'
        _setinterfaceparam(node, 'eth0', 'discoverytype', 'bmc')
        node['bmcpassword'] = 'initial0'
        try:
            hsnnics = node['hsnnics']
        except KeyError:
            node['hsnnics'] = 1
            hsnnics = 1
        try:
            hsngroupoffset = node['hsngroupoffset']
        except KeyError:
            node['hsngroupoffset'] = 1
            hsngroupoffset = 1
        for hsnnic in range(hsnnics):
            nic = 'hsn%d' % hsnnic
            group = (node['racknum'] % 1000) + hsngroupoffset
            switch = _hsnswitchnum(node['chassis'], node['board'],
                                   nicspernode=hsnnics, nic=hsnnic,
                                   nodesperboard=1, racktype='zeus')
            port = _hsnswitchport(node['slot'], node['nodenum'])

            _setinterfaceparam(node, nic, 'network', 'hsn')
            _setinterfaceparam(node, nic, 'group', group)
            _setinterfaceparam(node, nic, 'switchnum', switch)
            _setinterfaceparam(node, nic, 'port', port)
            _setinterfaceparam(node, nic, 'switch', _hsnswitchname(node['racknum'], node['chassis'], node['board'], hsnnics, hsnnic))
            _setinterfaceparam(node, nic, 'mac', _hsnalgomac(group, switch, port))

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
        _setinterfaceparam(node, 'me0', 'network', 'hostctrl')

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
        _setinterfaceparam(node, 'me0', 'network', 'hostctrl')

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
            _setinterfaceparam(node, 'eth0', 'hostname', node['name'])
            _setinterfaceparam(node, 'eth0', 'network', 'hostctrl')
        node['firmware_name'] = 'BMC'

    elif node['type'] == 'cec':
        node['ip6'] = "%s:0:a%d:%x:0" % (ipprefix, node['chassis'], node['racknum'])
        # The CECs live in a chassis, but remove this for now
        del node['chassis']

    logging.debug("Done running cray_ex plugin for node %s", node['name'])

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

def _hsnswitchchassisoffset(board, nicspernode, nic):
    if nicspernode == 1:
        if board == 0:
            whichswitchslot = 3
        elif board == 1:
            whichswitchslot = 7
    elif nicspernode == 4:
        if board == 0:
            if nic == 0 or nic == 1:
                whichswitchslot = 1
            else:
                whichswitchslot = 3
        else:
            if nic == 0 or nic == 1:
                whichswitchslot = 5
            else:
                whichswitchslot = 7
    return whichswitchslot

def _hsnswitchname(rack, chassis, board, nicspernode, nic):
    """ Determines the name of the HSN switch """
    whichswitchslot = _hsnswitchchassisoffset(board, nicspernode, nic)
    return "x%dc%dr%db0" % (rack, chassis, whichswitchslot)

def _hsnswitchnum(chassis, board, boardsperslot=2, nodesperboard=2,
                  nicspernode=1, nic=0, racktype='hill'):
    """ Return the (local) switch number
    """
    switchesperchassis = nicspernode * nodesperboard * boardsperslot / 2
    whichswitchslot = _hsnswitchchassisoffset(board, nicspernode, nic)
    if racktype == 'mountain' or racktype == 'olympus' or racktype == 'zeus':
        if switchesperchassis == 2:
            offset = [3, 7].index(whichswitchslot)
        elif switchesperchassis == 4:
            offset = [1, 3, 5, 7].index(whichswitchslot)
        elif switchesperchassis == 8:
            offset = whichswitchslot
        else:
            offset = 0
        return chassis * switchesperchassis + offset
    elif racktype == 'hill':
        # Hill cabinets only have 2 chassis labeled 1 and 3
        switchnum = board
        if chassis == 3:
            switchnum = switchnum + 2
        return switchnum
    return 0

def _hsnswitchport(slot, nodenum):
    return colorado_map[slot][nodenum]

if __name__ == '__main__':
    print(_hsnalgomac(1, 1, 47))
    print(_hsnalgomac(1, 1, colorado_map[0][0]))
