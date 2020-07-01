#!/usr/bin/env python
"""Node manager"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

from ClusterShell.NodeSet import NodeSet
from jinja2 import Template
from jinja2 import Environment
import re
import copy
import importlib
import ipaddress
import Phoenix
from Phoenix.System import System

class Node(object):
    tpl_regex = re.compile(r'{{')
    num_regex = re.compile(r'\d+')
    loaded_functions = False
    loaded_nodes = False
    environment = None

    plugins = dict()
    nodes = dict()

    def __init__(self, name):
        self.rawattr = dict()
        self.attr = {'name': name}
        self.ran_plugins = False

    def __repr__(self):
        #attrs = ["%s = %s (%s)" % (attr_name, getattr(self, attr_name), type(getattr(self, attr_name))) for attr_name in dir(self) if attr_name not in dir(Node)]
        if not self.ran_plugins:
            self.run_plugins()
        self.interpolate(None)
        return dump({self.attr['name']: self.attr}, default_flow_style=False)
        attrs = ["%s = %s (%s)" % (attr_name, self[attr_name], type(self[attr_name])) for attr_name in sorted(self.attr.keys() + self.rawattr.keys())]
        return "Node(%s)\n\t%s" % (self.attr['name'], "\n\t".join(attrs))

    def __setitem__(self, key, value):
        self.attr[key] = value

    def __getitem__(self, key):
        if not self.ran_plugins:
            self.run_plugins()
        if key in self.attr:
            return self.attr[key]
        if key not in self.rawattr:
            raise KeyError
        #self.attr[key] = self.interpolate(key)
        self.interpolate(key)
        #self.attr[key] = self.rawattr[key]
        #del self.rawattr[key]
        return self.attr[key]

    def __delitem__(self, key):
        del self.attr[key]

    def __contains__(self, key):
        if key in self.attr or key in self.rawattr:
            return True
        return False

    @classmethod
    def load_nodes(cls, filename=None, nodeset=None, clear=False):
        """ Reads and processes the nodes.yaml file.
            Can be called more than once to load multiple files,
            or if you want to focus on a different nodeset. By
            default, it just adds to the current view of nodes.
            Set clear=True to clear all currently-known nodes.
        """

        # Clear known nodes if requested
        if clear:
            cls.nodes = dict()

        if filename is None:
            filename = "%s/nodes.yaml" % Phoenix.conf_path

        # Read the yaml file
        logging.info("Loading node file '%s'", filename)
        with open(filename) as nodefd:
            nodedata = load(nodefd, Loader=Loader)

        # Load the data into the node structures
        for noderange, data in nodedata.items():
            ns1 = NodeSet(noderange)

            # Optimization to skip nodes we don't care about
            if nodeset is not None:
                ns1.intersection_update(nodeset)

            # If no nodes remain, move on to next section
            if ns1 is None or len(ns1) == 0:
                continue

            # This is where we should split out the keys between
            # simple values and complex ones (including needing interpolation)
            # Instead just do it below...

            for node in ns1:
                if node not in cls.nodes:
                    cls.nodes[node] = Node(node)
                for key, value in data.items():
                    # Deep copy is needed to make sure each node gets its own copy
                    #setattr(nodes[node], key, copy.deepcopy(value))
                    if not isinstance(value, str) or cls.tpl_regex.search(value):
                        cls.nodes[node].rawattr[key] = copy.deepcopy(value)
                        logging.debug("Setting node %s raw key %s to %s (%s)", node, key, value, cls.nodes[node].rawattr[key])
                    else:
                        cls.nodes[node][key] = value
                        logging.debug("Setting node %s key %s to %s", node, key, value)

        # Mark that nodes have been loaded
        cls.loaded_nodes = True

    @classmethod
    def find_node(cls, node):
        if not cls.loaded_nodes:
            cls.load_nodes()
        return cls.nodes[node]

    @classmethod
    def find_plugin(cls, name):
        if name not in cls.plugins:
            cls.plugins['name'] = importlib.import_module("Phoenix.Plugins.%s" % name)
        return cls.plugins['name']

    def run_plugins(self):
        if self.ran_plugins:
            return
        self.ran_plugins = True

        if 'plugin' in self.attr:
            plugin_name = self.attr['plugin']
        else:
            plugin_name = 'generic'

        logging.info("Running plugins for %s" % (self['name']))
        plugin = Node.find_plugin(plugin_name)
        plugin.set_node_attrs(self)

    @classmethod
    def ipadd(cls, base, offset):
        logging.debug("Called ipadd with %s and %d", base, offset)
        return str(System.find_network(base) + offset)
        if unicode(base[0], 'utf-8').isnumeric():
            return str(ipaddress.ip_address(unicode(base, "utf-8")) + offset)
        else:
            net = System.find_network(base)
            return str(net + offset)
        

    @classmethod
    def load_functions(cls):
        logging.info("Loading Jinja templates")
        cls.environment = Environment()
        cls.environment.globals['ipadd'] = Node.ipadd
        #Environment.globals['ipadd'] = Node.ipadd
        cls.loaded_functions = True

    def interpolatevalue(self, value):
        logging.debug("Interpolating value %s" % value)
        if not Node.loaded_functions:
            Node.load_functions()
        #return str(Template(value).render(**self.attr))
        return str(Node.environment.from_string(value).render(**self.attr))
        
    def interpolate(self, key=None, source=None, dest=None):
        """ Interpolates a value from source dict to dest dict.
            Key of None means interpolate all keys in the dict.
            Defaults to interpolating from the Node rawattr to attr
        """
        if source is None:
            source = self.rawattr
        if dest is None:
            dest = self.attr
        if key is None:
            # Interpolate everything in this dict
            for newkey in source.keys():
                self.interpolate(newkey, source, dest)
        elif isinstance(source[key], dict):
            newdest = dict()
            # This is a hierarchial value, recursively interpolate
            self.interpolate(None, source=source[key], dest=newdest)
            dest[key] = newdest
            del source[key]
        elif type(source[key]) == str:
            # Just interpolate one key in the dict
            dest[key] = self.interpolatevalue(source[key])
            del source[key]

    def run_command(self, client):
        try:
            #client.output("Running command %s for node %s" % (client.command, self.attr['name']))
            if isinstance(client.command, list):
                command = client.command[0]
                args = client.command[1:]
            else:
                command_parts = client.command.split()
                command = command_parts[0]
                args = command_parts[1:]
            if command == "power":
                try:
                    if args[0][0:3] == "pdu":
                        # Call the "normal" power commands (without pdu* prefix) against the PDU class"
                        args[0] = args[0][3:]
                        oobkind = "pdu"
                        oobtype = self['pdutype']
                        oobcls = _load_oob_class("pdu", oobtype)
                    else:
                        oobkind = "bmc"
                        oobtype = self['bmctype']
                except KeyError:
                    client.output("%stype not set" % oobkind, stderr=True)
                    rc=1
                else:
                    oobcls = _load_oob_class(oobkind, oobtype)
                    rc = oobcls.power(self, client, args)
            elif command == "firmware":
                oob = _load_oob_class("bmc", self['bmctype'])
                rc = oob.firmware(self, client, args)
            elif command == "inventory":
                oob = _load_oob_class("bmc", self['bmctype'])
                rc = oob.inventory(self, client, args)
            else:
                client.output("Unknown command '%s'" % command, stderr=True)
                rc = 1
            client.mark_command_complete(rc=rc)
        except Exception as e:
            client.output("Error running command: %s - %s" % (str(e), e.args), stderr=True)
            client.mark_command_complete(rc=1)

def _load_oob_class(oobtype, oobprovider):
    if oobprovider is None:
        logging.debug("Node does not have %stype set", oobtype)
        raise ImportError("Node does not have %stype set" % oobtype)
    logging.debug(oobprovider)
    #classname = oobprovider.lower().capitalize() + oobtype.lower().capitalize()
    classname = oobprovider.lower().capitalize()
    modname = "Phoenix.OOB.%s" % classname

    # Iterate over a copy of sys.modules' keys to avoid RuntimeError
    if modname.lower() not in [mod.lower() for mod in list(sys.modules)]:
        # Import module if not yet loaded
        __import__(modname)


    # Get the class pointer
    try:
        return getattr(sys.modules[modname], classname + oobtype.lower().capitalize())
    except:
        raise ImportError("Could not find class %s" % classname + oobtype.lower().capitalize())
