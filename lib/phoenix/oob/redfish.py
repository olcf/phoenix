#!/usr/bin/env python3
"""Redfish BMC Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import requests
import json
import re
import argparse
import collections.abc

from phoenix.oob import OOBTimeoutError
from phoenix.command import CommandTimeout
from phoenix.system import System

# This is needed to turn off SSL warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

import yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

from phoenix.oob import Oob

class RedfishError(Exception):
    pass

class Redfish(Oob):
    @classmethod
    def _do_redfish_req(cls, host, path, request_type, auth=('admin', 'password'), data={}, headers={}, timeout=(5,30), expand=False):
        """A simple redfish request - returns a requests response"""
        if expand:
            if '?' in path:
                path = path + '&$expand=.'
            else:
                path = path + '?$expand=.'
        url = "https://%s/redfish/v1/%s" % (host, path)
        logging.debug("Making %s request to %s", request_type, url)
        logging.debug("Data is %s", data)

        try:
            if request_type == "get":
                response = requests.get(url, verify=False, auth=auth, timeout=timeout)
            elif request_type == "post":
                response = requests.post(url, verify=False, auth=auth, headers=headers, json=data, timeout=timeout)
            elif request_type == "put":
                response = requests.put(url, verify=False, auth=auth, headers=headers, json=data, timeout=timeout)
            elif request_type == "patch":
                response = requests.patch(url, verify=False, auth=auth, headers=headers, json=data, timeout=timeout)
            else:
                raise NotImplementedError("HTTP request type %s not understood" % request_type)
        except requests.ConnectTimeout as e:
            raise OOBTimeoutError(e)
        except requests.ReadTimeout as e:
            raise OOBTimeoutError(e)
        except requests.ConnectionError as e:
            raise OOBTimeoutError(e)
        
        logging.debug("Response is %s", response.text)
        return response

    @classmethod
    def _get_redfish_attribute(cls, node, path, attr, status_codes=None, request_type="get", auth=None, expand=False):
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
        if expand:
            if 'redfishexpand' in node and not node['redfishexpand']:
                # TODO: emulate expand by looping through links
                raise NotImplementedError("BMC does not support expand")
        response = cls._do_redfish_req(node[cls.oobtype], path, request_type, auth, expand=expand)
        if status_codes is not None and response.status_code not in status_codes:
            return (False, "Redfish response returned status %d" % response.status_code)
        if len(response.content) == 0:
            return(False, "Redfish returned a blank response")
        value = response.json()
        if type(attr) is not list:
            attr = attr.split('.')
        try:
            for attrpath in attr:
                value = value[attrpath]
        except:
            return (False, "Redfish response JSON does not have attribute '%s'" % attr)
        return (True, value)

    @classmethod
    def _post_redfish(cls, node, path, data, status_codes=None, auth=None, method="post"):
        try:
            host = node[cls.oobtype]
        except:
            return (False, "Parameter %s not set on node" % cls.oobtype)
        if auth is None:
            auth = cls._get_auth(node)
        headers={'Content-Type': 'application/json'}
        response = cls._do_redfish_req(host, path, method, auth=auth, data=data, headers=headers)
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
            try:
                rjson = response.json()
                status = rjson
            except:
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
    def _redfish_attr(cls, name):
        """Node attribute name for this oobtype (pdu attributes are prefixed)"""
        return 'pdu_' + name if cls.oobtype == "pdu" else name

    @classmethod
    def _redfish_relpath(cls, uri):
        """Strip the service root from an @odata.id or action target"""
        uri = uri.rstrip('/')
        if uri.startswith('/redfish/v1/'):
            return uri[len('/redfish/v1/'):]
        return uri.lstrip('/')

    @classmethod
    def _redfish_path_linked(cls, node, kind, link, collection, auth=None):
        """Determine the best path to a resource related to the system: the
           node's redfish_<kind>_path attribute, else the first entry of the
           system's Links.<link>, else the first member of collection. The
           discovered path is cached on the node."""
        attr = cls._redfish_attr('redfish_%s_path' % kind)
        try:
            return node[attr]
        except KeyError:
            pass
        (ok, members) = cls._get_redfish_attribute(node, cls._redfish_path_system(node),
                                                   ['Links', link], auth=auth)
        if not ok or not members:
            (ok, members) = cls._get_redfish_attribute(node, collection, 'Members', auth=auth)
        if ok and members:
            path = cls._redfish_relpath(members[0]['@odata.id'])
        else:
            path = '%s/Self' % collection
        logging.debug("%s path is %s", kind, path)
        node[attr] = path
        return path

    @classmethod
    def _redfish_path_manager(cls, node, auth=None):
        return cls._redfish_path_linked(node, 'manager', 'ManagedBy', 'Managers', auth)

    @classmethod
    def _redfish_path_chassis(cls, node, auth=None):
        return cls._redfish_path_linked(node, 'chassis', 'Chassis', 'Chassis', auth)

    @classmethod
    def _redfish_target(cls, node, target=None, auth=None):
        """Resolve a power target to (path, actions attribute). Explicit
           paths have no actions attribute, so their actions are not cached."""
        if target is None:
            return (cls._redfish_path_system(node), cls._redfish_attr('redfish_actions'))
        if target == 'manager':
            return (cls._redfish_path_manager(node, auth), cls._redfish_attr('redfish_manager_actions'))
        if target == 'chassis':
            return (cls._redfish_path_chassis(node, auth), cls._redfish_attr('redfish_chassis_actions'))
        return (cls._redfish_relpath(target), None)

    @classmethod
    def _redfish_resource_type(cls, path):
        """Standard resource type for a path, used to build default targets"""
        collection = path.split('/')[0]
        return {'Chassis': 'Chassis', 'Managers': 'Manager'}.get(collection, 'ComputerSystem')

    @classmethod
    def _redfish_default_target(cls, path, action):
        """Names without a dot are reset types of the standard Reset action.
           Other actions are named <ResourceType>.<Action> and live under
           Actions/Oem unless the resource type is the standard one for the
           path."""
        resourcetype = cls._redfish_resource_type(path)
        if '.' not in action:
            return '%s/Actions/%s.Reset' % (path, resourcetype)
        if action.split('.')[0] == resourcetype:
            return '%s/Actions/%s' % (path, action)
        return '%s/Actions/Oem/%s' % (path, action)

    @classmethod
    def _redfish_is_reset_target(cls, target):
        """True if target is a standard (non-OEM) <ResourceType>.Reset action"""
        segments = target.rstrip('/').split('/')
        return len(segments) >= 2 and segments[-2] == 'Actions' and segments[-1].endswith('.Reset')

    @classmethod
    def _redfish_action_entries(cls, actions, oem=False):
        """Yield (name, action, oem) for each action, including OEM actions
           optionally nested under a vendor key"""
        for key, action in actions.items():
            if not isinstance(action, collections.abc.Mapping):
                continue
            if key.startswith('#'):
                yield (key[1:], action, oem)
            elif key == 'Oem' or oem:
                yield from cls._redfish_action_entries(action, oem=True)

    @classmethod
    def _redfish_discover_actions(cls, node, path, auth=None):
        """Query the actions a resource accepts. Each allowable ResetType of
           the standard Reset action maps to its target. Every other action,
           standard or OEM, maps to its target and the allowable values of
           its parameters."""
        (ok, actions) = cls._get_redfish_attribute(node, path, 'Actions', status_codes=[200], auth=auth)
        if not ok or not isinstance(actions, collections.abc.Mapping):
            logging.debug("Unable to discover actions for %s: %s", path, actions)
            return None
        discovered = dict()
        for name, action, oem in cls._redfish_action_entries(actions):
            if 'target' in action:
                target = cls._redfish_relpath(action['target'])
            elif oem:
                target = '%s/Actions/Oem/%s' % (path, name)
            else:
                target = '%s/Actions/%s' % (path, name)
            parameters = cls._redfish_action_parameters(node, action, auth)
            if not oem and cls._redfish_is_reset_target(target):
                for resettype in parameters.get('ResetType', []):
                    discovered[resettype] = target
            elif parameters:
                discovered[name] = {'target': target, 'parameters': parameters}
            else:
                discovered[name] = target
        return discovered

    @classmethod
    def _redfish_action_parameters(cls, node, action, auth=None):
        """Allowable values of each action parameter, from annotations on the
           action or its ActionInfo"""
        parameters = dict()
        for key, value in action.items():
            if key.endswith('@Redfish.AllowableValues'):
                parameters[key.split('@')[0]] = list(value)
        if '@Redfish.ActionInfo' in action:
            path = cls._redfish_relpath(action['@Redfish.ActionInfo'])
            try:
                (ok, params) = cls._get_redfish_attribute(node, path, 'Parameters', status_codes=[200], auth=auth)
            except (OOBTimeoutError, ValueError) as e:
                (ok, params) = (False, e)
            if not ok:
                logging.debug("No parameters from %s: %s", path, params)
            else:
                for param in params:
                    if 'Name' in param:
                        parameters.setdefault(param['Name'], list(param.get('AllowableValues', [])))
        return parameters

    @classmethod
    def _redfish_actions(cls, node, target=None, discover=True, auth=None):
        """Returns (path, actions) where actions maps each accepted action to
           a dict with its target and parameters. Actions come from the
           target's actions attribute (e.g. redfish_actions): a list of names,
           or a mapping of name to a target or to a mapping with target and
           parameters. If unset they are discovered and cached on the node."""
        (path, attr) = cls._redfish_target(node, target, auth)
        try:
            if attr is None:
                raise KeyError(path)
            configured = node[attr]
        except KeyError:
            if not discover:
                return (path, dict())
            configured = cls._redfish_discover_actions(node, path, auth)
            if not configured:
                return (path, dict())
            logging.debug("Discovered actions for %s: %s", path, configured)
            if attr is not None:
                node[attr] = configured
        if isinstance(configured, (str, bool)):
            configured = [configured]
        actions = dict()
        for name in configured:
            value = configured.get(name) if isinstance(configured, collections.abc.Mapping) else None
            name = cls._redfish_action_name(name)
            if isinstance(value, collections.abc.Mapping):
                target = value.get('target')
                parameters = value.get('parameters') or {}
            else:
                target = value
                parameters = {}
            target = target or cls._redfish_default_target(path, name)
            actions[name] = {
                'target': target,
                'reset': cls._redfish_is_reset_target(target),
                'parameters': {str(k): list(parameters[k] or []) for k in parameters},
            }
        return (path, actions)

    @classmethod
    def _redfish_value_str(cls, value):
        if isinstance(value, bool):
            return 'true' if value else 'false'
        return str(value)

    @classmethod
    def _redfish_action_name(cls, name):
        """YAML 1.1 loads unquoted On and Off as booleans"""
        if isinstance(name, bool):
            return 'On' if name else 'Off'
        return str(name)

    @classmethod
    def _redfish_format_action(cls, name, action):
        params = ['%s=%s' % (k, '|'.join(map(cls._redfish_value_str, v)) if v else '<value>')
                  for k, v in sorted(action['parameters'].items())]
        return '%s(%s)' % (name, ', '.join(params)) if params else name

    @classmethod
    def _redfish_action_body(cls, action, known, params, force):
        """Build the POST body for an action. params are KEY=VALUE strings, or
           a bare VALUE when the action has a single known parameter. Unless
           force is set, names and values are matched case-insensitively
           against the known parameters. Returns (ok, body or error)."""
        body = dict()
        for param in params:
            if '=' in param:
                (key, value) = param.split('=', 1)
            elif len(known) == 1:
                (key, value) = (list(known)[0], param)
            else:
                return (False, "Parameter '%s' must be given as KEY=VALUE" % param)
            if not force:
                names = {k.lower(): k for k in known}
                if key.lower() not in names:
                    return (False, "Unknown parameter %s for %s. Parameters: %s" %
                            (key, action, ', '.join(sorted(known)) or 'none'))
                key = names[key.lower()]
                allowed = [cls._redfish_value_str(v) for v in known[key]]
                values = {cls._redfish_value_str(v).lower(): v for v in known[key]}
                if values:
                    if value.lower() not in values:
                        return (False, "Invalid value %s for %s. Allowed: %s" %
                                (value, key, ', '.join(allowed)))
                    value = values[value.lower()]
            body[key] = value
        if not force:
            missing = sorted(k for k in known if known[k] and k not in body)
            if missing:
                return (False, "Missing parameter for %s: %s" %
                        (action, ', '.join('%s=%s' % (k, '|'.join(map(cls._redfish_value_str, known[k])))
                                           for k in missing)))
        return (True, body)

    @classmethod
    def _power_state(cls, node, auth=None, target=None):
        (redfishpath, _) = cls._redfish_target(node, target, auth)
        logging.debug("Inside _power_state %s", redfishpath)
        return cls._get_redfish_attribute(node, redfishpath, 'PowerState', status_codes=[200], auth=auth)

    @classmethod
    def _redfish_path_attr(cls, target):
        """Node attribute holding the path of a power target"""
        if target is None:
            return 'pduredfishpath' if cls.oobtype == "pdu" else 'redfishpath'
        return cls._redfish_attr('redfish_%s_path' % target)

    @classmethod
    def _redfish_actions_yaml(cls, path, attr, target, actions):
        """Node attributes, as YAML, that reproduce path and actions. Targets
           and parameters are only included where they differ from the
           defaults, and a plain list is used when none do."""
        entries = dict()
        for name in sorted(actions, key=str.lower):
            action = actions[name]
            entry = dict()
            if action['target'] != cls._redfish_default_target(path, name):
                entry['target'] = action['target']
            if action['parameters']:
                entry['parameters'] = action['parameters']
            if list(entry) == ['target']:
                entry = entry['target']
            entries[name] = entry or None
        if all(entry is None for entry in entries.values()):
            entries = list(entries)
        attrs = {cls._redfish_path_attr(target): path, attr: entries}
        dumped = yaml.safe_dump(attrs, default_flow_style=None, sort_keys=False, width=1000)
        return re.sub(r': null$', ':', dumped, flags=re.MULTILINE).rstrip()

    @classmethod
    def _power_actions(cls, node, auth=None, target=None, as_yaml=False):
        (path, actions) = cls._redfish_actions(node, target=target, auth=auth)
        if not actions:
            return (False, "No actions found for %s" % path)
        if as_yaml:
            (_, attr) = cls._redfish_target(node, target, auth)
            if attr is None:
                return (False, "Actions for an explicit target cannot be set as node attributes")
            return (True, cls._redfish_actions_yaml(path, attr, target, actions))
        return (True, ', '.join(cls._redfish_format_action(name, actions[name])
                                for name in sorted(actions, key=str.lower)))

    @classmethod
    def _power_action(cls, node, action, params=None, auth=None, target=None, force=False):
        params = params or []
        (path, actions) = cls._redfish_actions(node, target=target, discover=not force, auth=auth)
        names = {name.lower(): name for name in actions}
        if action.lower() in names:
            action = names[action.lower()]
            target = actions[action]['target']
            reset = actions[action]['reset']
            known = actions[action]['parameters']
        elif force:
            target = cls._redfish_default_target(path, action)
            reset = cls._redfish_is_reset_target(target)
            known = {}
        else:
            return (False, "Action %s not supported by %s. Supported actions: %s" %
                    (action, path, ', '.join(sorted(actions, key=str.lower)) or 'none found'))
        if reset:
            if params:
                return (False, "Reset type %s does not take parameters" % action)
            data = {'ResetType': action}
        else:
            (ok, data) = cls._redfish_action_body(action, known, params, force)
            if not ok:
                return (False, data)
        return cls._redfish_post_action(node, target, data, auth)

    @classmethod
    def _redfish_post_action(cls, node, target, data, auth=None):
        if auth is None:
            auth = cls._get_auth(node)
        host = node[cls.oobtype]
        headers = { 'Content-Type': 'application/json' }
        response = cls._do_redfish_req(host, target, "post", auth, data, headers)
        if response.status_code not in [200, 202, 204]:
            try:
                value = response.json()
                return (False, value['error']['message'])
            except:
                return (False, "Redfish response returned status %d" % response.status_code)
        # This usually just returns an empty body
        return (True, "Ok")

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
        if fwtype is None:
            try:
                return node['firmware_target']
            except KeyError:
                if fwtype is not None and fwtype.lower() == "recovery":
                    return '/redfish/v1/UpdateService/FirmwareInventory/Recovery'
                return None
        return '/redfish/v1/UpdateService/FirmwareInventory/%s' % fwtype

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
        (rc, msg) = cls._post_redfish(node, path, data, status_codes=[200, 202, 204])
        if isinstance(msg, dict):
            if '@odata.type' in msg and 'task' in msg['@odata.type'].lower():
                if 'Id' in msg:
                    message = 'Ok: Task %s created' % msg['Id']
            else:
                message = json.dumps(msg)
        else:
            message = msg
        return (rc, message)

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

    @classmethod
    def _bios(cls, node, args):
        systempath = cls._redfish_path_system(node)
        if not isinstance(args, argparse.Namespace):
            return (False, 'Called with incompatible client')
        if args.action is None:
            return (False, "No action specified")
        if args.action == "get":
            path = '%s/Bios' % (systempath)
            if args.parameter:
                rc, data = cls._get_redfish_attribute(node, path, "Attributes.%s" % args.parameter)
            else:
                rc, data = cls._get_redfish_attribute(node, path, "Attributes")
            try:
                if isinstance(data, dict):
                    data = yaml.dump(data, default_flow_style=False, explicit_start=False, explicit_end=False) 
            except Exception as e:
                pass
            return rc, data
        elif args.action == "set":
            if 'parameter' not in args or 'value' not in args:
                return(False, "Must specify a key and value (got %s)" % str(args))
            value = args.value
            if value.lower() == "false":
                value = False
            elif value.lower() == "true":
                value = True
            path = '%s/Bios/Settings' % (systempath)
            data = {"Attributes": { args.parameter: value }}
            (rc, msg) = cls._post_redfish(node, path, data, status_codes=[200, 202, 204], method='patch')
            if rc:
                msg = "Ok"
            return (rc, msg)
        elif args.action == "check":
            if 'biossettings' not in node:
                return(False, "Expected bios settings is not set on node %s" % node.name)
            msg = list()
            path = '%s/Bios' % (systempath)
            rc, data = cls._get_redfish_attribute(node, path, "Attributes")
            rc = 0
            for item, value in node['biossettings'].items():
                if item not in data:
                    msg.append("%s not found in bios response" % item)
                    rc = 1
                elif data[item] != value:
                    msg.append("%s got '%s' but expected '%s'" % (item, data[item], value))
                    rc = 1
            if rc == 0:
                return True, "Ok"
            return False, "\n".join(sorted(msg))
        elif args.action == "sync":
            if 'biossettings' not in node:
                return(False, "Expected bios settings is not set on node %s" % node.name)
            path = '%s/Bios/Settings' % (systempath)
            data = {"Attributes": dict(node['biossettings'])}
            (rc, msg) = cls._post_redfish(node, path, data, status_codes=[200, 202, 204], method='patch')
            if rc:
                msg = "Ok"
            return (rc, msg)
        elif args.action == 'bootorder':
            (rc, order) = cls._get_redfish_attribute(node, systempath, "Boot.BootOrder")
            path = '%s/BootOptions' % systempath
            (rc, details) = cls._get_redfish_attribute(node, path, 'Members', expand=True)
            output = list()
            bootmap = dict()
            for device in details:
                bootmap[device['Name']] = "%s - %s - %s" % (device['Name'], device['DisplayName'], device['UefiDevicePath'])
            if args.value is None:
                for device in order:
                    output.append(bootmap[device])
                return (rc, '\n'.join(output))
            else:
                target = None
                request = args.value
                if request in order:
                    target = request
                else:
                    pattern = re.compile(request)
                    for device in bootmap:
                        if re.search(pattern, bootmap[device]):
                            target = device
                            break
                    if target is None:
                        return(False, "%s not found" % request)
                order.insert(0, order.pop(order.index(target)))
                path = '%s/Settings' % (systempath)
                data = { "Boot": { "BootOrder": order }}
                (rc, msg) = cls._post_redfish(node, path, data, status_codes=[200, 202, 204], method='patch')
                if rc:
                    return(rc, 'Set %s as first boot device' % target)
                else:
                    return(rc, msg)
        elif args.action == 'password':
            if 'user' in args:
                user = args.user
            elif 'bmcuser' in node:
                user = node['bmcuser']
            else:
                user = 'root'
            if 'originalpassword' in args and args.originalpassword is not None:
                original = args.originalpassword
            elif 'bmcdefaultpassword' in node:
                original = node['bmcdefaultpassword']
            else:
                return(False, 'Original password unknown')
            if 'newpassword' in args and args.newpassword is not None:
                new = args.newpassword
            elif 'bmcpassword' in node:
                new = node['bmcpassword']
            else:
                return(False, 'New password unknown')
            payload = { 'Password': new }
            path = 'AccountService/Accounts/%s' % user
            (rc, msg) = cls._post_redfish(node, path, payload, status_codes=[200, 202, 204], method='patch', auth=(user, original))
            if rc:
                return(rc, 'Ok')
            else:
                return (rc, msg)
        else:
            return(False, "Unknown bios action '%s' for a redfish bmc" % args.action)

class RedfishBmc(Redfish):
    oobtype = "bmc"

class RedfishPdu(Redfish):
    oobtype = "pdu"
