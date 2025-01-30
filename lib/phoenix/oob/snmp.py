#!/usr/bin/env python3
"""SNMP out-of-band Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import netsnmp
import json

from phoenix.oob import OOBTimeoutError
from phoenix.oob import Oob

class SnmpError(Exception):
    pass

class Snmp(Oob):

    @classmethod
    def _snmpwalk(cls, oidd, hostname, community):
        session = netsnmp.Session(Version=2, DestHost=hostname, Community=community, Timeout=3000000, Retries=0)
        oid = netsnmp.VarList(netsnmp.Varbind(oidd))
        session.walk(oid)

        if session.ErrorStr != '':
            raise OOBTimeoutError

        for x in oid:
            yield x

class SnmpSwitch(Snmp):
    oobtype = "switch"
    dot1dBasePortIfIndex = '.1.3.6.1.2.1.17.1.4.1.2'
    dot1qTpFdbStatus = '.1.3.6.1.2.1.17.7.1.2.2.1.3'
    dot1qTpFdbPort = '.1.3.6.1.2.1.17.7.1.2.2.1.2'
    ifName = '.1.3.6.1.2.1.31.1.1.1.1'

    @classmethod
    def _switch_summary(cls, node):
        output = ['%-30s %s' % ('Interface', 'Mac (VLAN)')]
        summary_table = cls._switch_port_mac(node)
        logging.debug("%s", summary_table)
        for key, value in sorted(summary_table.items()):
            if len(value) > 2:
                macs = "<%d, likely uplink>" % len(value)
            else:
                macs = ", ".join(["%s (%d)" % (y[0], y[1]) for y in value])
            output.append("%-30s %s" % (key, macs))
        return "\n".join(output)

    @classmethod
    def _sort_interfaces(cls, key1, key2):
        parts = key.split('/')

    @classmethod
    def _switch_port_mac(cls, node):
        logging.debug("Inside _switch_port_mac for %s", node['name'])
        macmap = dict()
        hostname = node['name']
        try:
            community = node['community']
        except KeyError:
            community = 'public'
        idxmap = {}
        for x in cls._snmpwalk(cls.dot1dBasePortIfIndex, hostname, community):
            idx = (x.tag).split('.')[-1]
            idxmap[int(x.val)] = int(idx)
            #print x.val, " = ", idx
        idxmacstatemap = {}
        for x in cls._snmpwalk(cls.dot1qTpFdbStatus, hostname, community):
            parts = (x.tag).split('.')
            mac = ":".join(["%02x" % int(y) for y in parts[-6:]])
            idxmacstatemap[mac] = int(x.val)
            #print mac, int(x.val)
        idxmacmap = {}
        for x in cls._snmpwalk(cls.dot1qTpFdbPort, hostname, community):
            parts = (x.tag).split('.')
            vlan = int(parts[-7])
            mac = ":".join(["%02x" % int(y) for y in parts[-6:]])
            try:
                #print mac, idxmacstatemap[mac]
                if idxmacstatemap[mac] == 4:
                    continue
            except KeyError:
                # Weird, there wasn't a MAC state...
                continue
            idx = int(x.val)
            #print "%s %s" % (mac, idx)
            if idx not in idxmacmap:
                idxmacmap[idx] = list()
            idxmacmap[idx].append((mac, vlan))

        for x in cls._snmpwalk(cls.ifName, hostname, community):
            #parts = (x.tag).split('.')
            if x.val.lower().startswith("management") or x.val.lower().startswith("null") or x.val.lower().startswith("vlan"):
                continue
            idx = int(x.iid)
            try:
                secondaryidx = idxmap[idx]
                maclist = idxmacmap[secondaryidx]
            except KeyError:
                # Likely a management port or VLAN
                maclist = list()
            macmap[x.val] = maclist
        logging.debug("Done with _switch_port_mac for %s. %s", node['name'], macmap)
        return macmap

    @classmethod
    def _inventory(cls, node, args):
        action = args[0]
        if action == "macmap" or action == "macs":
            output = cls._switch_summary(node)
            return (True, output)
        elif action == "macmapjson":
            output = json.dumps(cls._switch_port_mac(node))
            return (True, output)
        else:
            return (False, "Action %s not implemented" % action)

class SnmpPdu(Snmp):
    oobtype = "pdu"
