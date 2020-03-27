#!/usr/bin/env python
"""Redfish BMC Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import requests

# This is needed to turn off SSL warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class Redfish(object):
    @classmethod
    def _do_redfish_req(cls, node, request_type, path="", data={}, header={}):
        url = "https://%s/redfish/v1/%s" % (node['bmc'], path)
        logging.debug("url: {0}".format(url))

        # XXX TODO Pull this from Phoenix
        auth = ('root', 'initial0')

        if request_type == "get":
            return requests.get(url, verify=False, auth=auth, timeout=10)
        elif request_type == "post":
            return requests.post(url, verify=False, auth=auth, headers=header, json=data, timeout=10)
        elif request_type == "put":
            return requests.put(url, verify=False, auth=auth, headers=header, json=data, timeout=10)

    @classmethod
    def power(cls, node, client, args):
        # Normalize the requested state
        state = args[0].lower() #the only arg is state
        logging.debug("state: {0}".format(state))
        headers = { 'Content-Type': 'application/json' }

        try:
            if state in ['stat', 'state', 'status']:
                path = 'Systems/%s' % node['redfishpath']
                response = cls._do_redfish_req(node, "get", path)
                rjson = response.json()
                client.output("%s" % rjson['PowerState'])
            elif state in ['on']:
                data = { 'ResetType': 'On' }
                path = 'Systems/%s/Actions/ComputerSystem.Reset' % node['redfishpath']
                response = cls._do_redfish_req(node, "post", path, data, headers)
            elif state in ['off']:
                data = { 'ResetType': 'ForceOff' }
                path = 'Systems/%s/Actions/ComputerSystem.Reset' % node['redfishpath']
                response = cls._do_redfish_req(node, "post", path, data, headers)
            #elif state in ['reset', 'restart']:
            #  data = { 'ResetType': 'ForceRestart' }
            #  path = 'Actions/ComputerSystem.Reset'
            #  response = _do_redfish_req(node, "post", path, data, headers)
            else:
                client.output("Invalid requested node state (%s)" % state, stderr=True)
                return -1
        except Exception as e:
            client.output("Redfish request failed: %s" % e, stderr=True)
            return -1

        # Current NCs are returning a 204 - need to test if this makes sense
        # Also figure out what an error response looks like and return it
        if response == -1:
            return "%s: Failed - status -1 (this is a phoenix error)" % (node)
        elif response.status_code == 200 or response.status_code == 204:
            #TODO: this should probably be more specific
            return "%s: Ok" % node
        else:
            return "%s: Failed - status %d" % (node, response.status_code)

    @classmethod
    def firmware(cls, node, client, args):
        # Normalize the requested command
        command = args[0].lower()

        try:
            if command in ['ver', 'version']:
                # This is definitely Olympus specific - move there!
                path = 'UpdateService/FirmwareInventory/Node%d.BIOS' % node['nodenum']
                response = cls._do_redfish_req(node, "get", path)
                rjson = response.json()
                client.output(rjson['Version'])
            elif command in ['stat', 'state', 'status']:
                # This is definitely Olympus specific - move there!
                path = 'UpdateService/FirmwareInventory/Node%d.BIOS' % node['nodenum']
                response = cls._do_redfish_req(node, "get", path)
                rjson = response.json()
                client.output(rjson['Status']['State'])
        except Exception as e:
            client.output("Redfish request failed: %s" % e, stderr=True)
            return -1
