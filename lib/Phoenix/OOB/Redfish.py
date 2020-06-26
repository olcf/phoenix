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
        """A simple redfish request - returns a requests response"""
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
    def _get_redfish_attribute(cls, node, path, attr, status_codes=None, request_type="get", auth=None):
        """A simple redfish request - returns a string with the requested attribute
           attr can be an array of nested paths, or a dot-separated path
           status_codes is an array of acceptable status codes
           """
        if auth is None:
            auth = cls._get_auth(node)
        response = cls._do_redfish_req(node['bmc'], path, request_type, auth)
        if status_codes is not None and response.status_code not in status_codes:
            return (False, "Redfish response returned status %d" % response.status_code)
        value = response.json()
        if type(attr) is not list:
            attr = attr.split('.')
        try:
            for attrpath in attr:
                value = value[attrpath]
        except:
            return (False, "Redfish response JSON does not have attribute '%s'" % attr)
        return (True, str(value))

    @classmethod
    def _redfish_path_system(cls, node):
        """Determine the best path the the System entry"""
        try:
            return node['redfishpath']
        except KeyError:
            return 'Systems/Self'

    @classmethod
    def _power_state(cls, node, auth=None):
        redfishpath = cls._redfish_path_system(node)
        return cls._get_redfish_attribute(node, redfishpath, 'PowerState', status_codes=[200], auth=auth)

    @classmethod
    def _redfish_reset(cls, node, resettype, auth=None):
        if auth is None:
            auth = cls._get_auth(node)
        redfishpath = cls._redfish_path_system(node)
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
        return cls._redfish_reset(node, 'ForceOff', auth)

    @classmethod
    def _redfish_path_firmware(cls, node, fwtype=None):
        """Determine the best path to the Firmware entries"""
        if fwtype is None:
            try:
                fwtype = node['firmware_name']
            except KeyError:
                fwtype = 'BIOS'
        return 'UpdateService/FirmwareInventory/%s' % fwtype

    @classmethod
    def _firmware_state(cls, node, fwtype=None, auth=None):
        path = cls._redfish_path_firmware(node, fwtype)
        return cls._get_redfish_attribute(node, path, ['Status', 'State'], auth=auth)

    @classmethod
    def _firmware_version(cls, node, fwtype=None, auth=None):
        path = cls._redfish_path_firmware(node, fwtype)
        return cls._get_redfish_attribute(node, path, ['Version'], auth=auth)

    inventory_map = {
        'mac': ('EthernetInterfaces/ManagementEthernet', 'MACAddress'),
        'ram': ('', 'MemorySummary.TotalSystemMemoryGiB'),
        'proccount': ('', 'ProcessorSummary.Count'),
        'proctype': ('', 'ProcessorSummary.Model'),
        }

    @classmethod
    def _inventory(cls, node, args):
        systempath = cls._redfish_path_system(node)
        if len(args) == 0:
            return (True, 'Summary is not currently supported')
        elif len(args) == 1:
            try:
                invitem = cls.inventory_map[args[0]]
                itempath = invitem[0]
                attr = invitem[1]
            except KeyError:
                return (False, "Unknown inventory item '%s'" % args[0])
        else:
            itempath = args[0]
            attr = args[1]

        path = '%s/%s' % (systempath, itempath)
        return cls._get_redfish_attribute(node, path, attr)
