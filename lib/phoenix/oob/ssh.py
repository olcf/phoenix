#!/usr/bin/env python3
"""OOB SSH Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import json

from ClusterShell.Task import Task
from phoenix.oob import OOBTimeoutError
from phoenix.oob import Oob

class SshError(Exception):
    pass

class Ssh(Oob):
    pass

class SshSwitch(Ssh):
    oobtype = "switch"

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
        ''' Currently only implemented for aruba'''
        logging.debug("Inside _switch_port_mac for %s", node['name'])
        macmap = dict()
        hostname = node['name']
        idxmap = {}
        task = Task()
        task.shell('show mac-address-table', nodes=hostname, timeout=10)
        task.resume()
        task.join()
        output = task.node_buffer(hostname)
        logging.debug(task.node_buffer(hostname))
        if task.max_retcode() != 0:
            logging.debug("An error occurred (max rc = %s)" % task.max_retcode())
        task.abort()
        for line in output.decode().split('\n'):
            try:
                (mac, vlan, porttype, port) = line.split()
                logging.debug("mac %s vlan %s type %s port %s", mac, vlan, porttype, port)
                if port not in macmap:
                    macmap[port] = list()
                macmap[port].append((mac, int(vlan)))
            except:
                pass
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

class SshPdu(Ssh):
    oobtype = "pdu"
