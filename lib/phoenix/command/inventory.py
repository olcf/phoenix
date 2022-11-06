#!/usr/bin/env python3
"""Inventory management"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import argparse

from ClusterShell.NodeSet import NodeSet
import phoenix
import phoenix.parallel
from phoenix.system import System
from phoenix.command import Command
from phoenix.oob import OOBTimeoutError

class InventoryCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="Query inventory of Phoenix nodes")
        parser.add_argument('nodes', default=None, type=str, help='Nodes to query')
        parser.add_argument('action', default=None, type=str, help='Action')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        phoenix.parallel.parser_add_arguments_parallel(parser)
        return parser

    @classmethod
    def cli(cls):
        parser = cls.get_parser()
        args = parser.parse_args()

        phoenix.setup_logging(args.verbose)
        nodes = NodeSet(args.nodes)
        (task, handler) = phoenix.parallel.setup(nodes, args)
        cmd = ["inventory", args.action]
        task.shell(cmd, nodes=nodes, handler=handler, autoclose=False, stdin=False, tree=True, remote=False)
        task.resume()
        rc = 0
        return rc

    @classmethod
    def run(cls, client):
        action = client.command[1]
        if client.node['type'] == 'switch':
            oobtype = 'snmp'
            oobcls = phoenix.get_component("oob", oobtype, oobtype.capitalize() + "Switch")
        else:
            oobkind = "bmc"
            try:
                oobtype = client.node['bmctype']
                oobcls = phoenix.get_component("oob", oobtype, oobtype.capitalize() + "Bmc")
            except KeyError:
                client.output("bmctype not set", stderr=True)
                return 1
        try:
            rc = oobcls.inventory(client.node, client, [action])
            return rc
        except OOBTimeoutError:
            client.output("Timeout", stderr=True)
            return rc
        except Exception as e:
            client.output("Error running command: %s - %s" % (str(e), e.args), stderr=True)
            return rc
