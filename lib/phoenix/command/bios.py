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
        subparsers = parser.add_subparsers(help='sub-command help', dest='action')
        parser_get = subparsers.add_parser('get', help='get a bios parameter')
        parser_get.add_argument('parameter', default=None, nargs='?', type=str, help='Parameter to get')
        parser_set = subparsers.add_parser('set', help='set a bios parameter')
        parser_set.add_argument('parameter', type=str, help='Parameter to set')
        parser_set.add_argument('value', type=str, help='Value to set')
        parser_check = subparsers.add_parser('check', help='Check bios parameters against configured')
        parser_sync = subparsers.add_parser('sync', help='Sync all bios parameters as configured')
        parser_bootorder = subparsers.add_parser('bootorder', help='Manage the bootorder')
        parser_bootorder.add_argument('value', default=None, nargs='?', type=str, help='Regex of a device to set as first boot device')
        parser_password = subparsers.add_parser('password', help='Set the BMC password')
        parser_password.add_argument('-o', '--original', dest='originalpassword', default=None, type=str, help='Original/old/current/factory password')
        parser_password.add_argument('-p', '--password', dest='newpassword', default=None, type=str, help='New password')
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
        cmd = ["bios", args]
        logging.debug("Submitting shell command %s", cmd)
        try:
            task.shell(cmd, nodes=nodes, handler=handler, autoclose=False, stdin=False, tree=True, remote=False)
            task.resume()
        except KeyboardInterrupt as kbe:
            print()
            phoenix.parallel.print_remaining(task, nodes, handler)
        except:
            logging.debug('CLI failed')
            raise
        rc = 0
        return rc

    @classmethod
    def run(cls, client):
        args = client.command[1]
        action = args.action
        oobkind = "bmc"
        try:
            oobtype = client.node['bmctype']
            oobcls = phoenix.get_component("oob", oobtype, oobtype.capitalize() + "Bmc")
        except KeyError:
            client.output("bmctype not set", stderr=True)
            client.mark_command_complete(rc=1)
            return 1
        try:
            rc = oobcls.bios(client.node, client, args)
            return rc
        except OOBTimeoutError:
            client.output("Timeout", stderr=True)
            return 1
        except Exception as e:
            client.output("Error running bios command: %s - %s" % (str(e), e.args), stderr=True)
            raise
            return 1

if __name__ == '__main__':
    sys.exit(PowerCommand.run())
