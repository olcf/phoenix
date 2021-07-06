#!/usr/bin/env python
"""Redfish BMC Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import requests

from phoenix.oob import OOBTimeoutError
from phoenix.command import CommandTimeout
from phoenix.system import System

# This is needed to turn off SSL warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from phoenix.oob import Oob

class RedfishError(Exception):
    pass

class Redfish(Oob):
    @classmethod
    def _do_redfish_req(cls, host, path, request_type, auth=('admin', 'password'), data={}, headers={}, timeout=(5,30)):
        """A simple redfish request - returns a requests response"""
        url = "https://%s/redfish/v1/%s" % (host, path)
        logging.debug("Making %s request to %s" % (request_type, url))
        logging.debug("Data is %s", data)

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
        except requests.ConnectionError as e:
            raise OOBTimeoutError(e)
        
        logging.debug("Response is %s", response.text)
        return response

    @classmethod
    def _get_redfish_attribute(cls, node, path, attr, status_codes=None, request_type="get", auth=None):
        """A simple redfish request - returns a string with the requested attribute
           attr can be an array of nested paths, or a dot-separated path
           status_codes is an array of acceptable status codes
           """
        try:
            host = node[cls.oobtype]
        except:
            return (False, "Parameter %s not set on node" % cls.oobtype)
        if auth is None:
            auth = cls._get_auth(node)
        response = cls._do_redfish_req(node[cls.oobtype], path, request_type, auth)
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
    def _post_redfish(cls, node, path, data, status_codes=None, auth=None):
        try:
            host = node[cls.oobtype]
        except:
            return (False, "Parameter %s not set on node" % cls.oobtype)
        if auth is None:
            auth = cls._get_auth(node)
        headers={'Content-Type': 'application/json'}
        response = cls._do_redfish_req(host, path, "post", auth=auth, data=data, headers=headers)
        logging.debug("Matt body is %s", response.request.body)
        logging.debug(str(status_codes))
        if status_codes is not None and response.status_code not in status_codes:
            try:
                rjson = response.json()
                value = rjson["error"]["message"]
            except:
                value = "Redfish response returned status %d" % response.status_code
            return (False, value)
        if len(response.text) == 0:
            status = "Ok"
        else:
            status = str(response.text)
        return (True, status)

    @classmethod
    def _redfish_get_systems(cls, node, auth=None):
        """Return a list of systems managed on this endpoint"""
        try:
            host = node[cls.oobtype]
        except:
            return list()
        if auth is None:
            auth = cls._get_auth(node)
        try:
            response = cls._do_redfish_req(host, "Systems", "get", auth=auth)
            value = response.json()
            members = value['Members']
            return [x['@odata.id'].split('/')[-1] for x in members]
        except:
            return list()

    @classmethod
    def _redfish_path_system(cls, node):
        """Determine the best path the the System entry"""
        if cls.oobtype == "bmc":
            try:
                return node['redfishpath']
            except KeyError:
                systems = cls._redfish_get_systems(node)
                logging.debug("Systems is %s", systems)
                system = "Systems/%s" % systems[0] if len(systems) > 0 else 'Systems/Self'
                # Save the detected value to avoid having to query the BMC again later
                node['redfishpath'] = system
                return system
        elif cls.oobtype == "pdu":
            try:
                return node['pduredfishpath']
            except KeyError:
                return 'Systems/Self'
        else:
            return 'Systems/Self'

    @classmethod
    def _redfish_path_simpleupdate(cls, node):
        """Determine the best path the the SimpleUpdate action"""
        try:
            return node['redfishsimpleupdate']
        except KeyError:
            return 'UpdateService/Actions/UpdateService.SimpleUpdate'

    @classmethod
    def _power_state(cls, node, auth=None):
        redfishpath = cls._redfish_path_system(node)
        logging.debug("Inside _power_state %s", redfishpath)
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
        if cls.oobtype == "bmc":
            host = node['bmc']
        elif cls.oobtype == "pdu":
            host = node['pdu']

        data = { 'ResetType': resettype }
        headers = { 'Content-Type': 'application/json' }
        response = cls._do_redfish_req(host, path, "post", auth, data, headers)
        if response.status_code not in [200, 202, 204]:
            try:
                value = response.json()
                return (False, value['error']['message'])
            except:
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
    def _redfish_target_firmware(cls, node, fwtype=None):
        try:
            return node['firmware_target']
        except KeyError:
            if fwtype is not None and fwtype.lower() == "recovery":
                return '/redfish/v1/UpdateService/FirmwareInventory/Recovery'
            return None

    @classmethod
    def _firmware_state(cls, node, fwtype=None, auth=None):
        path = cls._redfish_path_firmware(node, fwtype)
        return cls._get_redfish_attribute(node, path, ['Status', 'State'], auth=auth)

    @classmethod
    def _firmware_version(cls, node, fwtype=None, auth=None):
        path = cls._redfish_path_firmware(node, fwtype)
        return cls._get_redfish_attribute(node, path, ['Version'], auth=auth)

    @classmethod
    def _firmware_upgrade(cls, node, url, fwtype=None, auth=None):
        path = cls._redfish_path_simpleupdate(node)
        target = cls._redfish_target_firmware(node, fwtype)
        default_firmware = False
        if url is None:
            try:
                url = node['firmware']
                default_firmware = True
            except KeyError:
                return(False, 'Please specify a firmware URL')
        if not url.startswith('http'):
            try:
                firmwarebase = System.setting('firmware_base')
                url = firmwarebase + '/' + url
            except KeyError:
                return(False, 'Invalid firmware URL %s' % url)
        data = {"ImageURI": url, "TransferProtocol":"HTTP"}
        if target:
            data["Targets"] = [target]
        return cls._post_redfish(node, path, data, status_codes=[200, 202, 204])

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

class RedfishBmc(Redfish):
    oobtype = "bmc"

class RedfishPdu(Redfish):
    oobtype = "pdu"
