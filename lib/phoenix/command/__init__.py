#!/usr/bin/env python
"""Commands"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging

from ClusterShell.NodeSet import NodeSet
import phoenix
from phoenix.system import System

from phoenix.oob import OOBTimeoutError

class CommandTimeout(Exception):
    pass

class Command(object):
    def __init__(self, name):
        pass

    @classmethod
    def run(cls, client):
        logging.info("new run_command for %s and node %s", client.command, client.node)
        try:
            if isinstance(client.command, list):
                command = client.command[0]
                args = client.command[1:]
            else:
                command_parts = client.command.split()
                command = command_parts[0]
                args = command_parts[1:]
            if command == "power":
                try:
                    if args[0][0:3] == "pdu":
                        # Call the "normal" power commands (without pdu* prefix) against the PDU class"
                        args[0] = args[0][3:]
                        oobkind = "pdu"
                        oobtype = self['pdutype']
                        oobcls = _load_oob_class("pdu", oobtype)
                    else:
                        oobkind = "bmc"
                        oobtype = client.node['bmctype']
                except KeyError:
                    client.output("%stype not set" % oobkind, stderr=True)
                    rc=1
                else:
                    oobcls = _load_oob_class(oobkind, oobtype)
                    rc = oobcls.power(client.node, client, args)
            elif command == "firmware":
                oob = _load_oob_class("bmc", client.node['bmctype'])
                rc = oob.firmware(client.node, client, args)
            elif command == "inventory":
                oob = _load_oob_class("bmc", client.node['bmctype'])
                rc = oob.inventory(client.node, client, args)
            elif comand == "discover":
                oob = _load_oob_class("bmc", client.node['discovertype'])
                rc = oob.discover(client.node, client, args)
            else:
                client.output("Unknown command '%s'" % command, stderr=True)
                rc = 1
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
