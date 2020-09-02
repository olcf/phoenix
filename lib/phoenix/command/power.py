#!/usr/bin/env python
"""Power management"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import argparse

from ClusterShell.NodeSet import NodeSet
from jinja2 import Template
from jinja2 import Environment
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
	parser.add_argument('action', default=None, type=str, help='Action')
        parser.add_argument('--pdu', default=False, action='store_true', help='Target the PDU')
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
        cmd = ["power", args.action]
        if args.pdu:
            cmd.append("pdu")
        task.shell(cmd, nodes=nodes, handler=handler, autoclose=False, stdin=False, tree=True, remote=False)
        task.resume()
        rc = 0
        return rc

    @classmethod
    def run(cls, client):
        action = client.command[1]
        if 'pdu' in client.command:
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
            rc = oobcls.power(client.node, client, [action])
            client.mark_command_complete(rc=rc)
        except OOBTimeoutError:
            client.output("Timeout", stderr=True)
            client.mark_command_complete(rc=1)
        except Exception as e:
            client.output("Error running command: %s - %s" % (str(e), e.args), stderr=True)
            client.mark_command_complete(rc=1)

if __name__ == '__main__':
    sys.exit(PowerCommand.run())
