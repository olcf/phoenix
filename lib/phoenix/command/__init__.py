#!/usr/bin/env python
"""Commands"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import os

from ClusterShell.NodeSet import NodeSet
import phoenix
from phoenix.system import System

from phoenix.oob import OOBTimeoutError

class CommandTimeout(Exception):
    pass

class Command(object):
    @classmethod
    def run(cls, client):
        logging.info("Inside Command.run for %s and node %s", client.command, client.node['name'])
        try:
            if isinstance(client.command, list):
                command = client.command[0]
                args = client.command[1:]
            else:
                command_parts = client.command.split()
                command = command_parts[0]
                args = command_parts[1:]
            if command == "firmware":
                oob = _load_oob_class("bmc", client.node['bmctype'])
                rc = oob.firmware(client.node, client, args)
            elif command == "discover":
                oob = _load_oob_class("bmc", client.node['discovertype'])
                rc = oob.discover(client.node, client, args)
            else:
                cmdclass = phoenix.get_component('command', command)
                rc = cmdclass.run(client)
            client.mark_command_complete(rc=rc)
        except CommandTimeout:
            client._engine.remove(client, did_timeout=True)
        except OOBTimeoutError:
            client._engine.remove(client, did_timeout=True)
        except Exception as e:
            client.output("Error running command: %s - %s" % (str(e), e.args), stderr=True)
            client.mark_command_complete(rc=1)

def _load_oob_class(oobtype, oobprovider):
    if oobprovider is None:
        logging.debug("Node does not have %stype set", oobtype)
        raise ImportError("Node does not have %stype set" % oobtype)
    logging.debug("OOB type is %s, provider is %s", oobtype, oobprovider)
    return phoenix.get_component('oob', oobprovider, oobprovider.capitalize() + oobtype.capitalize())

class CommandClient(object):
    def output(self, message, stderr=False):
        print message

def run_command_cli():
    command = os.path.basename(sys.argv[0])
    if command.startswith('px'):
        command = command[2:]
    elif command == 'phoenix':
        sys.argv.pop(0)
        try:
            command = sys.argv[0]
        except IndexError:
            #logging.error("No action specified")
            return 1
    cmdclass = phoenix.get_component('command', command)
    return cmdclass.cli()
