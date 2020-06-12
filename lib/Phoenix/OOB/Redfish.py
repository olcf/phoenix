#!/usr/bin/env python
"""Redfish BMC Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import requests

from Phoenix.OOB import OOBTimeoutError

# This is needed to turn off SSL warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from Phoenix.OOB import OOB

class RedfishError(Exception):
    pass

class Redfish(OOB):
    @classmethod
    def _do_redfish_req(cls, bmc, path, request_type, auth=('admin', 'password'), data={}, headers={}, timeout=(5,30)):
        url = "https://%s/redfish/v1/%s" % (bmc, path)
        logging.debug("Making %s request to %s" % (request_type, url))

        try:
            if request_type == "get":
                response = requests.get(url, verify=False, auth=auth, timeout=timeout)
            elif request_type == "post":
                response = requests.post(url, verify=False, auth=auth, headers=headers, json=data, timeout=timeout)
            elif request_type == "put":
                response = requests.put(url, verify=False, auth=auth, headers=headers, json=data, timeout=timeout)
            else:
                raise NotImplementedError("HTTP request type %s not understood" % request_type)
        except requests.ConnectTimeout as e:
            raise OOBTimeoutError(e)
        
        logging.debug(response.text)
        return response

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
        response = cls._do_redfish_req(node['bmc'], redfishpath, "get", auth)
        if response.status_code != 200:
            return (False, "Redfish response returned status %d" % response.status_code)
        rjson = response.json()
        try:
            state = rjson['PowerState']
        except:
            return (False, "Redfish response JSON does not have a PowerState attribute")
        return (True, state)

    @classmethod
    def _redfish_reset(cls, node, resettype, auth=None):
        if auth is None:
            auth = cls._get_auth(node)
        redfishpath = cls._get_redfish_entity(node)
        if "Chassis" in redfishpath:
            path = '%s/Actions/Chassis.Reset' % redfishpath
        else:
            path = '%s/Actions/ComputerSystem.Reset' % redfishpath
        data = { 'ResetType': resettype }
        headers = { 'Content-Type': 'application/json' }
        response = cls._do_redfish_req(node['bmc'], path, "post", auth, data, headers)
        if response.status_code not in [200, 204]:
            return (False, "Redfish response returned status %d" % response.status_code)
        # This usually just returns an empty body
        return (True, "Ok")

    @classmethod
    def _power_on(cls, node, auth=None):
        return cls._redfish_reset(node, 'On', auth)

    @classmethod
    def _power_off(cls, node, auth=None):
        return cls._redfish_reset(node, 'Off', auth)

    @classmethod
    def _firmware_query(cls, node, fwtype=None, auth=None):
        if auth is None:
            auth = cls._get_auth(node)
        if fwtype is None:
            try:
                fwtype = node['firmware_name']
            except KeyError:
                fwtype = 'BIOS'
        path = 'UpdateService/FirmwareInventory/%s' % fwtype
        logging.debug(path)
        response = cls._do_redfish_req(node['bmc'], path, "get", auth)
        logging.debug(response.text)
        if response.status_code not in [200]:
            return(False, "Redfish response returned status %d" % response.status_code)
        try:
            return response.json()
        except:
            return (False, "Redfish response could not be parsed")

    @classmethod
    def _firmware_state(cls, node, fwtype=None, auth=None):
        rjson = cls._firmware_query(node, fwtype=fwtype, auth=auth)
        try:
            return (True, rjson['Status']['State'])
        except:
            return (False, "Redfish response could not be parsed")

    @classmethod
    def _firmware_version(cls, node, fwtype=None, auth=None):
        rjson = cls._firmware_query(node, fwtype=fwtype, auth=auth)
        try:
            return (True, rjson['Version'])
        except:
            return (False, "Redfish response could not be parsed")

