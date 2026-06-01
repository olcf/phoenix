#!/usr/bin/env python3
"""BIOS management"""
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

class BiosCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="Control the BIOS settings of Phoenix nodes")
        parser.add_argument('nodes', default=None, type=str, help='Nodes to list')
        parser.add_argument('action', default='get', nargs='?', type=str, help='Action')
        parser.add_argument('subject', default=None, nargs='?', type=str, help='Subject')
        parser.add_argument('value', default=None, nargs='?', type=str, help='Value to set')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        phoenix.parallel.parser_add_arguments_parallel(parser)
        return parser

    @classmethod
    def cli(cls):
        parser = cls.get_parser()
        args = parser.parse_args()

        phoenix.setup_logging(args.verbose)
        phoenix.adjust_limits()

        nodes = NodeSet(args.nodes)
        (task, handler) = phoenix.parallel.setup(nodes, args)
        cmd = ["bios", args.action, args.subject, args.value]
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
        action = client.command[1]
        oobkind = "bmc"
        try:
            oobtype = client.node['bmctype']
            oobcls = phoenix.get_component("oob", oobtype, oobtype.capitalize() + "Bmc")
        except KeyError:
            client.output("bmctype not set", stderr=True)
            client.mark_command_complete(rc=1)
            return 1
        try:
            rc = oobcls.bios(client.node, client, client.command)
            return rc
        except OOBTimeoutError:
            client.output("Timeout", stderr=True)
            return 1
        except Exception as e:
            client.output("Error running command: %s - %s" % (str(e), e.args), stderr=True)
            return 1

if __name__ == '__main__':
    sys.exit(PowerCommand.run())
