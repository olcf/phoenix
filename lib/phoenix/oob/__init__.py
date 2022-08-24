#!/usr/bin/env python
"""Generic Out-Of-Band Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import time # for sleep in reset - eventually remove
import logging

class OOBTimeoutError(Exception):
        pass

class Oob(object):
    oobtype = "unknown"

    @classmethod
    def _get_auth(cls, node):
        try:
            return (node['bmcuser'], node['bmcpassword'])
        except KeyError:
            return ('admin', 'password')

    @classmethod
    def power(cls, node, client, args):
        # Normalize the requested command
        command = args[0].lower()
        logging.debug("inside power command: {0}".format(command))

        #if command[0:3] == "pdu":
        #    command = command[3:]
        #    oobtype = "pdu"
        #else:
        #    oobtype = "bmc"
        #logging.debug("Type is %s", oobtype)

        try:
            if command in ['stat', 'state', 'status', 'query']:
                (ok, state) = cls._power_state(node, auth=cls._get_auth(node))
                client.output(state, stderr=not ok)
                return 0 if ok else 1
            elif command in ['on']:
                (ok,state) = cls._power_on(node, cls._get_auth(node))
                client.output(state, stderr=not ok)
                return 0 if ok else 1
            elif command in ['off']:
                (ok, state) = cls._power_off(node, cls._get_auth(node))
                client.output(state, stderr=not ok)
                return 0 if ok else 1
            elif command in ['forceoff']:
                (ok, state) = cls._power_forceoff(node, cls._get_auth(node))
                client.output(state, stderr=not ok)
                return 0 if ok else 1
            elif command in ['reset', 'restart']:
                try:
                    (ok, state) = cls._power_reset(node, cls._get_auth(node))
                    client.output(state, stderr=not ok)
                    return 0 if ok else 1
                except NotImplementedError:
                    # Fix to use off '--wait' instead of an arbitrary sleep
                    cls._power_off(node, cls._get_auth(node))
                    time.sleep(60)
                    cls._power_on(node, cls._get_auth(node))
                    client.output("Ok")
                    return 1
            else:
                client.output("Invalid requested node state command (%s)" % command, stderr=True)
                return -1
        except OOBTimeoutError as e:
            client.output("Connection timeout", stderr=True)
        except Exception as e:
            client.output("Power request failed: %s (%s)" % (type(e).__name__, e), stderr=True)
            raise

    @classmethod
    def _power_state(cls, node):
        raise NotImplementedError

    @classmethod
    def _power_on(cls, node):
        raise NotImplementedError

    @classmethod
    def _power_off(cls, node):
        raise NotImplementedError

    @classmethod
    def _power_reset(cls, node):
        raise NotImplementedError

    @classmethod
    def firmware(cls, node, client, args):
        # Normalize the requested command
        command = args.pop(0).lower()

        fwtype = None
        url = None
        if len(args) == 2:
            fwtype = args[0]
            url = args[1]
        elif len(args) == 1:
            if args[0].startswith('http'):
                url = args[0]
            else:
                fwtype = args[0]
        else:
            fwtype = None

        try:
            if command in ['ver', 'version']:
                (ok, state) = cls._firmware_version(node, fwtype=fwtype, auth=cls._get_auth(node))
                client.output(state, stderr=not ok)
                return 0 if ok else 1
            elif command in ['stat', 'state', 'status']:
                (ok, state) = cls._firmware_state(node, fwtype=fwtype, auth=cls._get_auth(node))
                client.output(state, stderr=not ok)
                return 0 if ok else 1
            elif command in ['up', 'update', 'upgrade']:
                (ok, state) = cls._firmware_upgrade(node, url, fwtype=fwtype, auth=cls._get_auth(node))
                client.output(state, stderr=not ok)
                return 0 if ok else 1
        except OOBTimeoutError as e:
            client.output("Connection timeout", stderr=True)
        except Exception as e:
            client.output("Firmware request failed: %s (%s)" % (type(e).__name__, e), stderr=True)
            return -1

    @classmethod
    def _firmware_version(cls, node):
        raise NotImplementedError

    @classmethod
    def _firmware_state(cls, node):
        raise NotImplementedError

    @classmethod
    def inventory(cls, node, client, args):
        try:
            (ok, state) = cls._inventory(node, args)
            client.output(state, stderr=not ok)
            return 0 if ok else 1
        except OOBTimeoutError as e:
            client.output("Connection timeout", stderr=True)
        except Exception as e:
            client.output("Inventory request failed: %s (%s)" % (type(e).__name__, e), stderr=True)
            return -1

    @classmethod
    def _inventory(cls, node):
        raise NotImplementedError

class Bmc(Oob):
    pass

class Pdu(Oob):
    pass

