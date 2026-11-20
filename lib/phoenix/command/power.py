#!/usr/bin/env python3
"""Power management"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import argparse

from ClusterShell.NodeSet import NodeSet
from jinja2 import Template
from jinja2 import Environment
import time
import re
import copy
import importlib
import ipaddress
import phoenix
import phoenix.parallel
from phoenix.system import System
from phoenix.command import Command
from phoenix.oob import OOBTimeoutError

class PowerCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="Control the power of Phoenix nodes")
        parser.add_argument('nodes', default=None, type=str, help='Nodes to list')
        parser.add_argument('action', default='stat', nargs='?', type=str,
                            help='stat, actions (list accepted actions), or an action such as On or ForceOff (case-insensitive)')
        parser.add_argument('params', nargs='*', type=str, metavar='PARAM',
                            help='Action parameters as KEY=VALUE, or VALUE when the action takes a single parameter')
        parser.add_argument('--pdu', default=False, action='store_true',
                            help='Use the upstream power device (pdu) instead of the node\'s BMC')
        target = parser.add_mutually_exclusive_group()
        target.add_argument('--manager', dest='target', action='store_const', const='manager',
                            help='Target the manager instead of the system')
        target.add_argument('--chassis', dest='target', action='store_const', const='chassis',
                            help='Target the chassis instead of the system')
        target.add_argument('--target', dest='target', metavar='PATH',
                            help='Target an explicit resource path (e.g. Chassis/Board0)')
        parser.add_argument('--force', default=False, action='store_true',
                            help='Send the action without checking it against the accepted actions')
        parser.add_argument('--wait', default=None, metavar='STATE', type=str,
                            help='Wait until the power state matches STATE (e.g. On or Off)')
        parser.add_argument('--yaml', default=False, action='store_true',
                            help='With actions, print them as node attributes for nodes.yaml')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        phoenix.parallel.parser_add_arguments_parallel(parser)
        return parser

    @classmethod
    def cli(cls):
        parser = cls.get_parser()
        args = parser.parse_args()
        if args.yaml and args.action.lower() != 'actions':
            parser.error('--yaml only applies to actions')

        phoenix.setup_logging(args.verbose)
        phoenix.adjust_limits()

        nodes = NodeSet(args.nodes)
        (task, handler) = phoenix.parallel.setup(nodes, args)
        cmd = ["power", args]
        logging.debug("Submitting shell command %s", cmd)
        try:
            task.shell(cmd, nodes=nodes, handler=handler, autoclose=False, stdin=False, tree=True, remote=False)
            task.resume()
        except KeyboardInterrupt as kbe:
            print()
            phoenix.parallel.print_remaining(task, nodes, handler)
        rc = 0
        return rc

    @classmethod
    def run(cls, client):
        args = client.command[1]
        if args.pdu:
            oobkind = "pdu"
            try:
                oobtype = client.node['pdutype']
                oobcls = phoenix.get_component("oob", oobtype, oobtype.capitalize() + "Pdu")
            except KeyError:
                client.output("pdutype not set", stderr=True)
                client.mark_command_complete(rc=1)
                return 1
        else:
            oobkind = "bmc"
            try:
                oobtype = client.node['bmctype']
                oobcls = phoenix.get_component("oob", oobtype, oobtype.capitalize() + "Bmc")
            except KeyError:
                client.output("bmctype not set", stderr=True)
                client.mark_command_complete(rc=1)
                return 1
        try:
            rc = oobcls.power(client.node, client, [args.action] + args.params, target=args.target, force=args.force,
                              as_yaml=args.yaml)
            if rc == 0 and args.wait:
                if not oobcls._wait_for_power_state(client.node, client, args.wait, target=args.target):
                    client.output("Timed out waiting for %s" % args.wait, stderr=True)
                    rc = 1
            return rc
        except OOBTimeoutError:
            client.output("Timeout", stderr=True)
            return 1
        except Exception as e:
            client.output("Error running command: %s - %s" % (str(e), e.args), stderr=True)
            return 1

if __name__ == '__main__':
    sys.exit(PowerCommand.run())
