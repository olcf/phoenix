#!/usr/bin/env python
"""Node manager"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import platform
import yaml
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
import phoenix
from phoenix.system import System

# Technically, maps in yaml are unordered. We want entries in nodes.yaml
# to be processed in the order present in the file so that overriding
# works the way one might expect. pyyaml stores mapping in a python dict()
# which was unordered until CPython 3.6 and made a language feature in 3.7.
# Use an OrderedDict for older python versions.
if sys.version_info < (3,7) or (sys.version_info < (3,6) and platform.python_implementation == "CPython"):
    from collections import OrderedDict

    def odict_constructor(loader, node):
        return OrderedDict(loader.construct_pairs(node))

    yaml.add_constructor("tag:yaml.org,2002:map", odict_constructor, Loader=Loader)

class Node(object):
    tpl_regex = re.compile(r'{{')
    num_regex = re.compile(r'\d+')
    loaded_functions = False
    loaded_nodes = False
    datasource = None
    environment = None

    plugins = dict()
    nodes = dict()

    def __init__(self, name):
        self.rawattr = dict()
        self.attr = {'name': name, 'type': 'generic'}
        self.ran_plugins = False

    def __repr__(self):
        #attrs = ["%s = %s (%s)" % (attr_name, getattr(self, attr_name), type(getattr(self, attr_name))) for attr_name in dir(self) if attr_name not in dir(Node)]
        if not self.ran_plugins:
            self.run_plugins()
        self.interpolate(None)
        return yaml.dump({self.attr['name']: self.attr}, default_flow_style=False)
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
        if not self.ran_plugins:
            self.run_plugins()
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
            filename = "%s/nodes.yaml" % phoenix.conf_path

        # Read the yaml file
        logging.info("Loading node file '%s'", filename)
        with open(filename) as nodefd:
            nodedata = yaml.load(nodefd, Loader=Loader)

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
                    if isinstance(value, bool) or (isinstance(value, str) and not cls.tpl_regex.search(value)):
                        cls.nodes[node][key] = value
                        logging.debug("Setting node %s key %s to %s", node, key, value)
                    else:
                        # Deep copy is needed to make sure each node gets its own copy
                        cls.nodes[node].rawattr[key] = copy.deepcopy(value)
                        logging.debug("Setting node %s raw key %s to %s (%s)", node, key, value, cls.nodes[node].rawattr[key])

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
            cls.plugins['name'] = importlib.import_module("phoenix.plugins.%s" % name)
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
    def data(cls, *args):
        logging.debug("Called data with key %s", args)
        if cls.datasource is None:
            cls.datasource = phoenix.get_component('datasource')
        logging.debug("calling getkey")
        output = cls.datasource.getval(*args)
        logging.debug("got data value %s", output)
        return output

    @classmethod
    def load_functions(cls):
        logging.info("Loading Jinja templates")
        cls.environment = Environment()
        cls.environment.globals['ipadd'] = Node.ipadd
        cls.environment.globals['data'] = Node.data
        #Environment.globals['ipadd'] = Node.ipadd
        cls.loaded_functions = True

    def interpolatevalue(self, value):
        logging.debug("Interpolating value %s" % value)
        if not Node.loaded_functions:
            Node.load_functions()
        #return str(Template(value).render(**self.attr))
        output = str(Node.environment.from_string(value).render(**self.attr))
        logging.debug("Interpolated value %s as %s", value, output)
        return output
        
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
        elif type(source[key]) == bool:
            dest[key] = source[key]
            del source[key]
