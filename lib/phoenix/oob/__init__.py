#!/usr/bin/env python3
"""Generic Out-Of-Band Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import time
import logging

class OOBTimeoutError(Exception):
        pass

class Oob(object):
    oobtype = "unknown"

    POWER_STATE_COMMANDS = ('stat', 'state', 'status', 'query')

    # Seconds to wait for a node to reach a requested power state
    power_wait_timeout = 180

    @classmethod
    def _get_auth(cls, node):
        try:
            return (node['bmcuser'], node['bmcpassword'])
        except KeyError:
            return ('admin', 'password')

    @classmethod
    def power(cls, node, client, args, target=None, force=False, as_yaml=False):
        """Run a power command. args[0] is a state query, 'actions', or an
           action, followed by any action parameters. target selects what
           to act on: None for the node itself, 'manager', 'chassis', or an
           explicit resource path. as_yaml prints 'actions' as node
           attributes."""
        command = args[0]
        params = list(args[1:])
        logging.debug("inside power command: %s (target=%s, force=%s)", command, target, force)

        try:
            auth = cls._get_auth(node)
            if command.lower() in cls.POWER_STATE_COMMANDS:
                (ok, state) = cls._power_state(node, auth=auth, target=target)
            elif command.lower() == 'actions':
                (ok, state) = cls._power_actions(node, auth=auth, target=target, as_yaml=as_yaml)
            else:
                (ok, state) = cls._power_action(node, command, params, auth=auth, target=target, force=force)
            client.set_state(state)
            client.output(state, stderr=not ok)
            return 0 if ok else 1
        except OOBTimeoutError as e:
            client.output("Connection timeout", stderr=True)
            return 1
        except Exception as e:
            client.output("Power request failed: %s (%s)" % (type(e).__name__, e), stderr=True)
            raise

    @classmethod
    def _wait_for_power_state(cls, node, client, desired, target=None, timeout=None):
        """Poll the power state until it matches desired or timeout expires.
           Returns True if the state was reached."""
        if timeout is None:
            timeout = cls.power_wait_timeout
        desired = desired.lower()
        for _ in range(timeout):
            time.sleep(1)
            cls.power(node, client, ['stat'], target=target)
            if client.state is not None and str(client.state).lower() == desired:
                return True
        return False

    @classmethod
    def _power_state(cls, node, auth=None, target=None):
        raise NotImplementedError

    @classmethod
    def _power_actions(cls, node, auth=None, target=None, as_yaml=False):
        """Returns (ok, message) listing the actions the target accepts, or
           with as_yaml, the node attributes that configure them"""
        raise NotImplementedError

    @classmethod
    def _power_action(cls, node, action, params=None, auth=None, target=None, force=False):
        """Sends action, with optional parameters, to the target. Unless force
           is set, the action must match (case-insensitively) one the target
           accepts."""
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
            if args[0].startswith('http') or command in ['up', 'update', 'upgrade']:
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

    @classmethod
    def bios(cls, node, client, args):
        try:
            (ok, state) = cls._bios(node, args)
            client.output(state, stderr=not ok)
            return 0 if ok else 1
        except OOBTimeoutError as e:
            client.output("Connection timeout", stderr=True)
        except Exception as e:
            client.output("BIOS request failed: %s (%s)" % (type(e).__name__, e), stderr=True)
            return -1

    @classmethod
    def _bios(cls, node, args):
        raise NotImplementedError

class Bmc(Oob):
    pass

class Pdu(Oob):
    pass

