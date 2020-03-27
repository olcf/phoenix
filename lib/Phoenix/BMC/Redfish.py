#!/usr/bin/env python
"""Redfish BMC Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import requests

# This is needed to turn off SSL warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from Phoenix.BMC import BMC

class RedfishError(Exception):
    pass

class Redfish(BMC):
    @classmethod
    def _do_redfish_req(cls, bmc, path, request_type, auth=('admin', 'password'), data={}, headers={}, timeout=(5,30)):
        url = "https://%s/redfish/v1/%s" % (bmc, path)
        logging.debug("url: {0}".format(url))

        if request_type == "get":
            return requests.get(url, verify=False, auth=auth, timeout=timeout)
        elif request_type == "post":
            return requests.post(url, verify=False, auth=auth, headers=headers, json=data, timeout=timeout)
        elif request_type == "put":
            return requests.put(url, verify=False, auth=auth, headers=headers, json=data, timeout=timeout)
        else:
            raise NotImplementedError("HTTP request type %s not understood" % request_type)

    @classmethod
    def _get_redfish_entity(cls, node):
        try:
            return node['redfishpath']
        except KeyError:
            return 'Self'

    @classmethod
    def _power_state(cls, node, auth=None):
        if auth is None:
            auth = cls._get_auth(node)
        redfishpath = cls._get_redfish_entity(node)
        path = 'Systems/%s' % redfishpath
        response = cls._do_redfish_req(node['bmc'], path, "get", auth)
        if response.status_code != 200:
            return (False, "Redfish response returned status %d" % response.status_code)
        rjson = response.json()
        try:
            state = rjson['PowerState']
        except:
            return (False, "Redfish response JSON does not have a PowerState attribute")
        return (True, state)

    @classmethod
    def _redfish_computer_reset(cls, node, resettype, auth=None):
        if auth is None:
            auth = cls._get_auth(node)
        redfishpath = cls._get_redfish_entity(node)
        path = 'Systems/%s/Actions/ComputerSystem.Reset' % redfishpath
        data = { 'ResetType': resettype }
        headers = { 'Content-Type': 'application/json' }
        response = cls._do_redfish_req(node['bmc'], path, "post", auth, data, headers)
        if response.status_code not in [200, 204]:
            return (False, "Redfish response returned status %d" % response.status_code)
        # This usually just returns an empty body
        return (True, "Ok")

    @classmethod
    def _power_on(cls, node, auth=None):
        return cls._redfish_computer_reset(node, 'On', auth)

    @classmethod
    def _power_off(cls, node, auth=None):
        return cls._redfish_computer_reset(node, 'Off', auth)

    @classmethod
    def firmware2(cls, node, client, args):
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
                pass
        except Exception as e:
            client.output("Redfish request failed: %s" % e, stderr=True)
            return -1

    @classmethod
    def _firmware_state(cls, node, auth=None):
        if auth is None:
            auth = cls._get_auth(node)
        # This is definitely Olympus specific - move there!
        path = 'UpdateService/FirmwareInventory/Node%d.BIOS' % node['nodenum']
        response = cls._do_redfish_req(node['bmc'], path, "get", auth)
        if response.status_code not in [200]:
            return(False, "Redfish response returned status %d" % response.status_code)
        rjson = response.json()
        try:
            return (True, rjson['Status']['State'])
        except:
            return (False, "Redfish response could not be parsed")

    @classmethod
    def _firmware_version(cls, node, auth=None):
        if auth is None:
            auth = cls._get_auth(node)
        # This is definitely Olympus specific - move there!
        path = 'UpdateService/FirmwareInventory/Node%d.BIOS' % node['nodenum']
        response = cls._do_redfish_req(node['bmc'], path, "get", auth)
        if response.status_code not in [200]:
            return(False, "Redfish response returned status %d" % response.status_code)
        rjson = response.json()
        try:
            return (True, rjson['Version'])
        except:
            return (False, "Redfish response could not be parsed")

