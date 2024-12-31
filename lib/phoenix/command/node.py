#!/usr/bin/env python3
"""Node configuration"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import sys
import argparse
import traceback

import yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

from ClusterShell.NodeSet import NodeSet

import phoenix
import phoenix.parallel
from phoenix.command import Command
from phoenix.node import Node

class NodeCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="List info about Phoenix nodes")
        parser.add_argument('nodes', nargs=1, default=None, type=str, help='Nodes to list')
        parser.add_argument('field', nargs='?', default=None, type=str, help='Field to show')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        phoenix.parallel.parser_add_arguments_parallel(parser)
        return parser

    @classmethod
    def cli(cls):
        parser = cls.get_parser()
        args = parser.parse_args()

        phoenix.setup_logging(args.verbose)

        nodes = NodeSet.fromlist(args.nodes)
        (task, handler) = phoenix.parallel.setup(nodes, args)
        task.shell(["node", args.field], nodes=nodes, handler=handler, autoclose=False, stdin=False, tree=True, remote=False)
        task.resume()
        rc = 0
        return rc

    @classmethod
    def run(cls, client):
        logging.debug("Inside command.node.run")
        rc=0
        try:
            if type(client.command) == list and len(client.command) > 1 and client.command[1] != None:
                val = cls.get_node_attr(client.node, client.command[1])
                if type(val) == str or type(val) == int:
                    client.output(str(val))
                else:
                    client.output(yaml.dump(val))
            else:
                # Show the whole node as YAML
                client.output("%s" % client.node)
        except Exception as e:
            if logging.getLogger().getEffectiveLevel() < logging.WARNING:
                client.output(traceback.format_exc(), stderr=True)
            else:
                client.output("Exception: %s" % repr(e), stderr=True)
            rc=1
        return rc

    @classmethod
    def get_node_attr(cls, node, attribute):
        if '.' in attribute:
            firstdot = attribute.find('.')
            return cls.get_node_attr(node[attribute[0:firstdot]], attribute[firstdot+1:])
        return node[attribute]

if __name__ == '__main__':
    sys.exit(NodeCommand.run())
