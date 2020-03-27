#!/usr/bin/env python
"""Generic BMC Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import time # for sleep in reset - eventually remove
import logging

class BMC(object):
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
        logging.debug("command: {0}".format(command))

        try:
            if command in ['stat', 'state', 'status', 'query']:
                (ok, state) = cls._power_state(node, cls._get_auth(node))
                client.output(state, stderr = not ok)
                return 0 if ok else 1
            elif command in ['on']:
                (ok,state) = cls._power_on(node, cls._get_auth(node))
                if ok:
                    client.output("Ok")
                return 0 if ok else 1
            elif command in ['off']:
                ok = cls._power_off(node, cls._get_auth(node))
                if ok:
                    client.output("Ok")
                return 0 if ok else 1
            elif command in ['reset', 'restart']:
                try:
                    ok = cls._power_reset(node, cls._get_auth(node))
                    if ok:
                        client.output("Ok")
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
        except Exception as e:
            client.output("Redfish request failed: %s (%s)" % (type(e).__name__, e), stderr=True)
            return -1

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
        command = args[0].lower()

        try:
            if command in ['ver', 'version']:
                (ok, state) = cls._firmware_version(node, cls._get_auth(node))
                client.output(state, stderr = not ok)
                return 0 if ok else 1
            elif command in ['stat', 'state', 'status']:
                (ok, state) = cls._firmware_state(node, cls._get_auth(node))
                client.output(state, stderr = not ok)
                return 0 if ok else 1
            elif command in ['update', 'upgrade']:
                (ok, state) = cls._firmware_upgrade(node, cls._get_auth(node))
                client.output(state, stderr = not ok)
                return 0 if ok else 1
        except Exception as e:
            client.output("Redfish request failed: %s (%s)" % (type(e).__name__, e), stderr=True)
            return -1

    @classmethod
    def _firmware_version(cls, node):
        raise NotImplementedError

    @classmethod
    def _firmware_state(cls, node):
        raise NotImplementedError
