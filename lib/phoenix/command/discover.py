#!/usr/bin/env python
"""Power management"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import argparse
import json

from ClusterShell.NodeSet import NodeSet
import phoenix
import phoenix.parallel
from phoenix.system import System
from phoenix.command import Command
from phoenix.node import Node

class DiscoverCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="Discover nodes")
        parser.add_argument('nodes', default=None, type=str, help='Nodes to try to find')
        parser.add_argument('--interface', '-i', default=[], type=str, action='append', dest='interfaces', help='Interfaces to discover')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        phoenix.parallel.parser_add_arguments_parallel(parser)
        return parser

    @classmethod
    def cli(cls):
        parser = cls.get_parser()
        args = parser.parse_args()

        phoenix.setup_logging(args.verbose)
        nodes = NodeSet(args.nodes)
        Node.load_nodes()

        individual_nodes = NodeSet()
        group_nodes = NodeSet()
        switches = NodeSet()

        for node in nodes:
            node = Node.find_node(node)
            if 'interfaces' not in node:
                logging.info('Interfaces not present, skipping')
                continue
            for interfacename in node['interfaces']:
                if len(args.interfaces) > 0 and interfacename not in args.interfaces:
                    logging.info('Requested interface not present, skipping')
                    continue
                interface = node['interfaces'][interfacename]
                if 'discoverytype' not in interface:
                    logging.info('Discoverytype, skipping %s', interfacename)
                    continue
                if interface['discoverytype'] == 'bmc':
                    individual_nodes.update(node['name'])
                elif interface['discoverytype'] == 'switch':
                    if 'switch' not in interface:
                        continue
                    if 'switchport' not in interface:
                        continue
                    switches.update(interface['switch'])
                    group_nodes.update(node['name'])

        data = phoenix.get_component('datasource')

        if len(individual_nodes) > 0:
            (task, _) = phoenix.parallel.setup(individual_nodes, args)
            cmd = ["inventory", "mac"]
            task.shell(cmd, nodes=individual_nodes, autoclose=False, stdin=False, tree=True, remote=False)
            task.resume()
            for buf, nodes in task.iter_buffers():
                for node in nodes:
                    print "%s is %s" % (node, buf)
                    data.setval('mac', node, buf)

        switchdata = dict()
        if len(group_nodes) > 0:
            logging.info("Checking switches now")
            (task, _) = phoenix.parallel.setup(switches, args)
            cmd = ["inventory", "macmapjson"]
            task.shell(cmd, nodes=switches, autoclose=False, stdin=False, tree=True, remote=False)
            task.resume()
            for buf, nodes in task.iter_buffers():
                for node in nodes:
                    logging.debug("Got buffer %s", buf)
                    switchdata[node] = json.loads(str(buf))

        logging.debug("group_nodes is %s", group_nodes)
        for nodename in group_nodes:
            logging.debug("Doing group_nodes %s", nodename)
            node = Node.find_node(nodename)
            for interfacename in node['interfaces']:
                logging.debug("Checking interface %s", interfacename)
                if len(args.interfaces) > 0 and interfacename not in args.interfaces:
                    logging.info("Skipping interface %s, not specified on command line", interfacename)
                    continue
                interface = node['interfaces'][interfacename]
                if 'discoverytype' not in interface:
                    logging.info("Skipping interface %s, discoverytype not set", interfacename)
                    continue
                if interface['discoverytype'] != 'switch':
                    logging.info("Skipping interface %s, discoverytype is not switch", interfacename)
                    continue
                try:
                    # TODO: If no match is found, try smart substring matching
                    maclist = switchdata[interface['switch']][interface['switchport']]
                    # TODO: add VLAN matching and "rules" to pick what interface to use instead of the first
                    mac = maclist[0][0]
                except Exception as e:
                    logging.debug(e)
                    logging.error("No mac address found for %s", nodename)
                    continue
                print "Node %s mac is %s" % (node['name'], mac)
                data.setval('mac', nodename, mac)

        rc = 0
        return rc

    @classmethod
    def run(cls, client):
        ''' Run the action for a single host (this is one instance of a parallel request '''
        action = client.command[1]
        client.output("Not yet implemented", stderr=True)
        return 1

if __name__ == '__main__':
    sys.exit(DiscoverCommand.run())
