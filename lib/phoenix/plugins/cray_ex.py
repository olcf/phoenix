#!/usr/bin/env python3
"""Plugin for HPE Cray EX machines"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import re
import os
import csv
from ClusterShell.NodeSet import NodeSet
from phoenix.system import System
from phoenix.network import Network
from phoenix.network import handleautointerfaces
from phoenix.node import Node
from phoenix.data import Data

cray_ex_regex = re.compile(r'x(?P<racknum>\d+)(?P<chassistype>[ce])(?P<chassis>\d+)((?P<slottype>[rs])(?P<slot>\d+)(b(?P<board>\d+)(n(?P<nodenum>\d+))?)?)?')
num_regex = re.compile(r'.*?(\d+)$')
ipprefix = 'fc00:0:100:60'

rosetta_group = dict()
rosetta_swcnum = dict()

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
    'autoip':       {},
    'nicspernode':  1,
}

try:
    usersettings = System.setting('cray_ex')
    settings.update(usersettings)
except:
    logging.error("cray_shasta section not found in system settings")
if 'racks' in settings:
    settings['racknodeset'] = NodeSet(settings['racks'])
    settings['racklist'] = list(settings['racknodeset'])
    if 'emptyracks' in settings:
        settings['racklistnonempty'] = list(settings['racknodeset'].difference(NodeSet(settings['emptyracks'])))
    else:
        settings['racklistnonempty'] = settings['racklist']
else:
    logging.error("racks not set in system.yaml cray_shasta section")
if type(settings['autoip']) == str:
    settings['autoip'] = { settings['autoip']: 0 }
elif type(settings['autoip']) == list:
    settings['autoip'] = dict.fromkeys(settings['autoip'], 0)

def read_rosetta():
    if not os.path.exists('/etc/phoenix/rosetta_map.csv'):
        return
    with open('/etc/phoenix/rosetta_map.csv', 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        for row in reader:
            rosetta_group[row[0]] = int(row[1])
            rosetta_swcnum[row[0]] = int(row[2])

def _hostctrl_network(node):
    global settings
    if settings.get('hostctrlvlanmode', 'rack-based') == 'sequential':
        return settings['hostctrlvlanstart'] + node['rackidx']
    else:
        return node['racknum'] - int(settings['racklist'][0][1:]) + settings['hostctrlvlanstart']

def _hostmgmt_network(node):
    global settings
    if settings.get('hostmgmtvlanmode', 'rack-based') == 'sequential':
        return settings['hostmgmtvlanstart'] + node['rackidx']
    else:
        return node['racknum'] - int(settings['racklist'][0][1:]) + settings['hostmgmtvlanstart']

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

    # This is purely convention
    racknum = node['racknum']
    if racknum >= 1000 and racknum <= 2999:
        node['racktype'] = 'mountain'
    elif racknum >= 3000 and racknum <= 4999:
        node['racktype'] = 'river'
    elif racknum >= 9000 and racknum <= 9999:
        node['racktype'] = 'hill'

    if 'type' not in node:
        if 'nodenum' in node:
            node['type'] = 'compute'
        elif 'slot' in node:
            slottype = m.group('slottype')
            if slottype == 'r':
                node['type'] = 'switch'
            elif 'board' in node:
                node['type'] = 'nc'
            else:
                node['type'] = 'blade'
        elif 'chassis' in node:
            chassistype = m.group('chassistype')
            if chassistype == 'e':
                node['type'] = 'cec'
            else:
                node['type'] = 'cc'

    try:
        node['rackidx'] = settings['racklist'].index(node['rack'])
        node['rackidxnonempty'] = settings['racklistnonempty'].index(node['rack'])
    except:
        # This could be a columbia switch, for example
        pass

    if 'type' in node and node['type'] == 'compute':
        # FIXME: Make this configurable (support Hill and grizzly peak)
        nodesperchassis = settings['nodesperrack']//8
        nodesperslot = nodesperchassis//8
        nodesperboard = nodesperslot//2
        node['nodeindexinrack'] = (nodesperchassis * node['chassis'] +
                                   nodesperslot * node['slot'] +
                                   nodesperboard * node['board'] +
                                   node['nodenum']
                                  )
        node['nodeindex'] = (settings['nodesperrack'] * node['rackidx'] +
                             node['nodeindexinrack'] +
                             settings['startnid']
                            )

    if 'nodeindex' not in node and node['racktype'] == 'river':
        m = num_regex.match(node['name'])
        if m is not None:
            node['nodeindex'] = int(m.group(1))

def _nid_to_node_attrs(node):
    ''' If a node has nodeindex set, try to figure out the xname details'''
    global settings
    logging.debug("Inside _nid_to_node_attrs for node %s", node['name'])

    if 'nodeindex' not in node:
        logging.debug("nodeindex not set for node %s", node['name'])
        return

    if 'type' not in node:
        node['type'] = 'compute'

    # FIXME: Make this configurable (support Hill and grizzly peak)
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
    if 'racklistnonempty' in settings:
        node['rackidxnonempty'] = settings['racklistnonempty'].index(node['rack'])
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

    read_rosetta()

    # FIXME: This won't do the right thing if you system name starts with 'x'
    #        Hopefully that won't bite us any time soon...
    #        Could instead have a lightweight regex, but that might hurt
    #        performance too much
    if 'xname' in node:
        logging.debug("Node has an xname defined on the node attribute")
        _xname_to_node_attrs(node)
    elif node['name'].startswith('x'):
        logging.debug("Node name %s is an xname", node['name'])
        node['xname'] = node['name']
        _xname_to_node_attrs(node)
        if 'rack' not in node:
            logging.error("Could not parse xname")
            return
    elif alias is not None and alias.startswith('x'):
        logging.debug("Node alias %s is an xname", alias)
        node['xname'] = alias
        _xname_to_node_attrs(node)
        if 'rack' not in node:
            logging.error("Could not parse xname")
            return
    elif 'type' in node and node['type'] == 'compute':
        logging.debug("Node name %s is NOT an xname", node['name'])
        m = num_regex.match(node['name'])
        if m is not None:
            node['nodeindex'] = int(m.group(1))
            _nid_to_node_attrs(node)

    if 'xname' not in node:
        logging.error("Cray EX component %s does not have an xname", node['name'])
        return

    if node['type'] == 'compute':
        node['redfishpath'] = 'Systems/Node%d' % node['nodenum']
        node['firmware_name'] = 'Node%d.BIOS' % node['nodenum']
        node['firmware_target'] = '/redfish/v1/UpdateService/FirmwareInventory/Node%d.BIOS' % node['nodenum']
        node['bmctype'] = 'redfish'
        node['bmc'] = "x{racknum}c{chassis}s{slot}b{board}".format(**node.attr)
        node['bmcuser'] = 'root'
        node['discoverytype'] = 'bmc'
        if 'hostmgmt' in settings['autoip']:
            _setinterfaceparam(node, 'bond0', 'network', 'hostmgmt%d' % _hostmgmt_network(node))
            _setinterfaceparam(node, 'bond0', 'ip', Network.ipadd("hostmgmt", node['nodeindexinrack'] + settings['autoip']['hostmgmt'], node['rackidx']))
            _setinterfaceparam(node, 'bond0', 'mac', Data.data('mac', node['name']))
            _setinterfaceparam(node, 'bond0', 'alias', node['xname'])
        _setinterfaceparam(node, 'bond0', 'discoverytype', 'bmc')
        node['bmcpassword'] = 'initial0'
        node['pdu'] = "x{racknum}c{chassis}".format(**node.attr)
        node['pdutype'] = 'redfish'
        node['pduuser'] = 'root'
        node['pdupassword'] = 'initial0'
        node['pduredfishpath'] = 'Chassis/Blade%d' % node['slot']
        globalnicspernode = settings['nicspernode']
        try:
            hsnnics = node['hsnnics']
        except KeyError:
            node['hsnnics'] = globalnicspernode
            hsnnics = globalnicspernode
        try:
            hsngroupoffset = node['hsngroupoffset']
        except KeyError:
            node['hsngroupoffset'] = 1
            hsngroupoffset = 1
        for hsnnic in range(hsnnics):
            nic = 'hsn%d' % hsnnic
            switchname = _hsnswitchname(node['racknum'], node['chassis'], node['board'], globalnicspernode, hsnnic)
            if switchname in rosetta_group:
                group = rosetta_group[switchname]
            else:
                if 'rackidxnonempty' in node:
                    group = node['rackidxnonempty'] + hsngroupoffset
                else:
                    group = node['rackidx'] + hsngroupoffset
            switch = _hsnswitchnum(node['chassis'], node['board'],
                                   nicspernode=globalnicspernode, nic=hsnnic,
                                   nodesperboard=1, racktype='zeus',
                                   switchname=switchname)
            port = _hsnswitchport(node['slot'], node['nodenum'], hsnnics, hsnnic)

            _setinterfaceparam(node, nic, 'network', 'hsn')
            _setinterfaceparam(node, nic, 'group', group)
            _setinterfaceparam(node, nic, 'switchnum', switch)
            _setinterfaceparam(node, nic, 'port', port)
            _setinterfaceparam(node, nic, 'switch', switchname)
            _setinterfaceparam(node, nic, 'mac', _hsnalgomac(group, switch, port))
            if 'hsn' in settings['autoip']:
                _setinterfaceparam(node, nic, 'ip', Network.ipadd("hsn", (node['nodeindex'] * globalnicspernode) + hsnnic + settings['autoip']['hsn']))

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
        if 'hostctrl' in settings['autoip']:
            offset = node['chassis'] * 16 + node['slot'] * 2 + node['board']
            _setinterfaceparam(node, 'me0', 'network', 'hostctrl%d' % _hostctrl_network(node))
            _setinterfaceparam(node, 'me0', 'ip', Network.ipadd("hostctrl", offset + 100 + settings['autoip']['hostctrl'], node['rackidx']))

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
        if 'hostctrl' in settings['autoip']:
            _setinterfaceparam(node, 'me0', 'network', 'hostctrl')
            _setinterfaceparam(node, 'me0', 'ip', Network.ipadd("hostctrl", node['chassis'] + settings['autoip']['hostctrl'], node['rackidx']))

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
            if 'hostctrl' in settings['autoip']:
                _setinterfaceparam(node, 'eth0', 'network', 'hostctrl%d' % _hostctrl_network(node))
                offset = node['chassis'] * 8 + node['slot']
                _setinterfaceparam(node, 'eth0', 'ip', Network.ipadd("hostctrl", offset + 20 + settings['autoip']['hostctrl'], node['rackidx']))

        node['firmware_name'] = 'BMC'

    elif node['type'] == 'cec':
        node['ip6'] = "%s:0:a%d:%x:0" % (ipprefix, node['chassis'], node['racknum'])
        # The CECs live in a chassis, but remove this for now
        del node['chassis']

    # This needs to eventually move to models instead of polluting every node
    if 'racktype' not in node or node['racktype'] != 'river' or node['type'] == 'switch':
        node['redfishsimpleupdate'] = 'UpdateService/Actions/SimpleUpdate'

    # Autointerfaces currently doesn't support "adding" to interfaces
    # This will blow away anything defined previously
    if 'autointerfaces' in node:
        handleautointerfaces(node)

    logging.debug("Done running cray_ex plugin for node %s", node['name'])

def _setinterfaceparam(node, interface, paramname, paramvalue):
    """ Updates a node's interface with a certain value """
    if paramvalue == None:
        return
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
                whichswitchslot = 3
            else:
                whichswitchslot = 1
        else:
            if nic == 0 or nic == 1:
                whichswitchslot = 7
            else:
                whichswitchslot = 5
    return whichswitchslot

def _hsnswitchname(rack, chassis, board, nicspernode, nic):
    """ Determines the name of the HSN switch """
    whichswitchslot = _hsnswitchchassisoffset(board, nicspernode, nic)
    return "x%dc%dr%db0" % (rack, chassis, whichswitchslot)

def _hsnswitchnum(chassis, board, boardsperslot=2, nodesperboard=2,
                  nicspernode=1, nic=0, racktype='hill', switchname=None):
    """ Return the (local) switch number
    """
    if switchname is not None and switchname in rosetta_swcnum:
        return rosetta_swcnum[switchname]
    switchesperchassis = nicspernode * nodesperboard * boardsperslot // 2
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

def _hsnswitchport(slot, nodenum, nicspernode=1, nic=0):
    if nicspernode == 1:
        return colorado_map[slot][nodenum]
    elif nicspernode == 4:
        if nic == 0 or nic == 3:
            return colorado_map[slot][1]
        else:
            return colorado_map[slot][0]

if __name__ == '__main__':
    print(_hsnalgomac(1, 1, 47))
    print(_hsnalgomac(1, 1, colorado_map[0][0]))
