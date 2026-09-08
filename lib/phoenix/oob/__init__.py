#!/usr/bin/env python3
"""Generic Out-Of-Band Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import time
import logging

class OOBTimeoutError(Exception):
        pass

class Oob(object):
    oobtype = "unknown"

    # Accepted command line words mapped to canonical power actions
    POWER_ALIASES = {
        'stat': 'state',
        'state': 'state',
        'status': 'state',
        'query': 'state',
        'on': 'on',
        'forceon': 'forceon',
        'off': 'off',
        'forceoff': 'forceoff',
        'gracefulshutdown': 'gracefulshutdown',
        'reset': 'reset',
        'restart': 'reset',
        'forcerestart': 'reset',
        'gracefulrestart': 'gracefulrestart',
        'powercycle': 'powercycle',
    }

    # Actions that can be emulated with off/on when unsupported natively
    POWER_RESTART_ACTIONS = ('reset', 'gracefulrestart', 'powercycle')

    # Terminal power state each action settles into, for --wait. Restart
    # actions are omitted since they end in the same state they started.
    POWER_WAIT_STATES = {
        'on': 'on',
        'forceon': 'on',
        'off': 'off',
        'forceoff': 'off',
        'gracefulshutdown': 'off',
    }

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
            action = cls.POWER_ALIASES[command]
        except KeyError:
            client.output("Invalid requested node state command (%s). Valid commands: %s" %
                          (command, ', '.join(sorted(cls.POWER_ALIASES))), stderr=True)
            return -1

        try:
            method = getattr(cls, '_power_%s' % action)
            try:
                (ok, state) = method(node, cls._get_auth(node))
            except NotImplementedError:
                if action not in cls.POWER_RESTART_ACTIONS:
                    raise
                # No native restart action; emulate it by powering off,
                # waiting for the node to reach Off, then powering on. Confirm
                # both halves exist first so we never strand a node powered off.
                if not cls._can_emulate_restart():
                    client.output("%s is not supported by %s and cannot be emulated" %
                                  (command, cls.__name__), stderr=True)
                    return 1
                (ok, state) = cls._power_off(node, cls._get_auth(node))
                if not ok:
                    client.set_state(state)
                    client.output(state, stderr=True)
                    return 1
                if not cls._wait_for_power_state(node, client, 'off'):
                    client.output("Timed out waiting for Off", stderr=True)
                    return 1
                (ok, state) = cls._power_on(node, cls._get_auth(node))
            client.set_state(state)
            client.output(state, stderr=not ok)
            return 0 if ok else 1
        except OOBTimeoutError as e:
            client.output("Connection timeout", stderr=True)
        except Exception as e:
            client.output("Power request failed: %s (%s)" % (type(e).__name__, e), stderr=True)
            raise

    @classmethod
    def _can_emulate_restart(cls):
        """True if off/on/state are all implemented, so a restart can be
           emulated without risk of leaving the node powered off."""
        for name in ('_power_off', '_power_on', '_power_state'):
            if getattr(cls, name).__func__ is getattr(Oob, name).__func__:
                return False
        return True

    # Seconds to wait for a node to reach a requested power state
    power_wait_timeout = 180

    @classmethod
    def _wait_for_power_state(cls, node, client, desired, timeout=None):
        """Poll the power state until it matches desired or timeout expires.
           Each poll refreshes client state so --wait output stays live.
           Returns True if the state was reached."""
        if timeout is None:
            timeout = cls.power_wait_timeout
        desired = desired.lower()
        for _ in range(timeout):
            time.sleep(1)
            cls.power(node, client, ['stat'])
            if client.state is not None and str(client.state).lower() == desired:
                return True
        return False

    @classmethod
    def _power_state(cls, node, auth=None):
        raise NotImplementedError

    @classmethod
    def _power_on(cls, node, auth=None):
        raise NotImplementedError

    @classmethod
    def _power_off(cls, node, auth=None):
        raise NotImplementedError

    @classmethod
    def _power_forceon(cls, node, auth=None):
        raise NotImplementedError

    @classmethod
    def _power_forceoff(cls, node, auth=None):
        raise NotImplementedError

    @classmethod
    def _power_gracefulshutdown(cls, node, auth=None):
        raise NotImplementedError

    @classmethod
    def _power_reset(cls, node, auth=None):
        raise NotImplementedError

    @classmethod
    def _power_gracefulrestart(cls, node, auth=None):
        raise NotImplementedError

    @classmethod
    def _power_powercycle(cls, node, auth=None):
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

