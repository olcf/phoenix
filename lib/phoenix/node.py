#!/usr/bin/env python3
"""Node manager"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import platform
import types
import yaml
import os
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
from phoenix.network import Network
from phoenix.data import Data

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
    loaded_nodemap = False
    datasource = None
    environment = None

    plugins = dict()
    nodes = dict()
    nodemap = dict()
    nodeset_cache = dict()
    models = dict()

    def __init__(self, name):
        self.rawattr = dict()
        self.rawattr_nodeset_index = dict()
        self.attr = {'name': name}
        self.ran_plugins = False

    def __repr__(self):
        #attrs = ["%s = %s (%s)" % (attr_name, getattr(self, attr_name), type(getattr(self, attr_name))) for attr_name in dir(self) if attr_name not in dir(Node)]
        if not self.ran_plugins:
            self.run_plugins()
        self.interpolate(None)
        return yaml.dump({self.attr['name']: self.attr}, default_flow_style=False)
        attrs = ["%s = %s (%s)" % (attr_name, self[attr_name], type(self[attr_name])) for attr_name in sorted(self.attr.keys() + self.rawattr.keys())]
        return "Node(%s)\n\t%s" % (self.attr['name'], "\n\t".join(attrs))

    def setrawitem(self, key, value):
        self.rawattr[key] = value

    def setifblank(self, key, value):
        if key not in self:
            self.attr[key] = value

    def __setitem__(self, key, value):
        self.attr[key] = value

    def __getitem__(self, key):
        if not self.ran_plugins:
            self.run_plugins()
        if key in self.attr:
            if type(self.attr[key]) is types.LambdaType:
                return self.attr[key]()
            return self.attr[key]
        if key in self.rawattr:
            self.interpolate(key)
            return self.attr[key]
        try:
            return Node.models[self.attr['model']][key]
        except:
            raise KeyError(key)

    def __delitem__(self, key):
        del self.attr[key]

    def __contains__(self, key):
        if key in self.attr or key in self.rawattr:
            return True
        if not self.ran_plugins:
            self.run_plugins()
            if key in self.attr or key in self.rawattr:
                return True
        if 'model' in self.attr and self.attr['model'] in Node.models and key in Node.models[self.attr['model']]:
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
            nodedata = yaml.load(nodefd, Loader=Loader) or {}

        # Load the data into the node structures
        for noderange, data in nodedata.items():
            ns1 = NodeSet(noderange)

            # This is where we should split out the keys between
            # simple values and complex ones (including needing interpolation)
            # Instead just do it below...

            for node_nodeset_index, node in enumerate(ns1):
                # Optimization to skip nodes we don't care about
                if nodeset is not None and node not in nodeset:
                    continue
                if node not in cls.nodes:
                    cls.nodes[node] = Node(node)
                for key, value in data.items():
                    if (isinstance(value, bool) or
                        isinstance(value, int) or
                        isinstance(value, float) or
                        (isinstance(value, str) and not cls.tpl_regex.search(value))
                       ):
                        cls.nodes[node][key] = value
                        logging.debug("Setting node %s key %s to %s", node, key, value)
                    else:
                        # Deep copy is needed to make sure each node gets its own copy
                        newval = copy.deepcopy(value)
                        if isinstance(value, dict):
                            if key not in cls.nodes[node].rawattr:
                                cls.nodes[node].rawattr[key] = dict()
                            cls.nodes[node].rawattr[key].update(newval)
                        else:
                            cls.nodes[node].rawattr[key] = newval
                        cls.nodes[node].rawattr_nodeset_index[key] = node_nodeset_index
                        logging.debug("Setting node %s raw key %s to %s (%s) - offset %d", node, key, value, cls.nodes[node].rawattr[key], node_nodeset_index)

        # Mark that nodes have been loaded
        cls.loaded_nodes = True

    @classmethod
    def _load_nodemap(cls, filename=None, ndoeset=None, clear=False):
        """ Reads and processes a nodemap yaml file
        """

        if clear:
            cls.nodemap = dict()

        if filename is None:
            filename = "%s/nodemap.yaml" % phoenix.conf_path

        # Read the yaml file
        logging.info("Trying to load nodemap file '%s'", filename)
        try:
            with open(filename) as nodemapfd:
                nodemapdata = yaml.load(nodemapfd, Loader=Loader) or {}

            cls.nodemap.update(nodemapdata)
            cls.nodemap.update({v: k for k, v in nodemapdata.items()})
        except:
            logging.info("Could not load nodemap")

        cls.loaded_nodemap = True

    @classmethod
    def find_node(cls, node):
        if not cls.loaded_nodes:
            cls.load_nodes()
        try:
            return cls.nodes[node]
        except KeyError:
            if not cls.loaded_nodemap:
                cls._load_nodemap()
            try:
                n2 = cls.nodemap[node]
                logging.debug("Didn't find node %s but nodemap maps that to %s", node, n2)
            except:
                logging.debug("Nodemap did not map %s", node)
                raise KeyError(node)
            return cls.nodes[n2]

    @classmethod
    def node_alias(cls, node):
        logging.debug("Inside node_alias")
        if not cls.loaded_nodemap:
            logging.debug("Node_alias calling load_nodemap")
            cls._load_nodemap()
        try:
            return cls.nodemap[node]
        except:
            logging.debug("No alias found for %s", node)
            return None

    @classmethod
    def find_plugin(cls, name):
        logging.debug("Inside find_plugin")
        if name not in cls.plugins:
            try:
                cls.plugins['name'] = importlib.import_module("phoenix.plugins.%s" % name)
            except Exception as e:
                logging.debug(e)
                raise
        return cls.plugins['name']

    def run_plugins(self):
        if self.ran_plugins:
            return
        self.ran_plugins = True

        if 'plugin' in self.attr:
            plugin_name = self.attr['plugin']
        else:
            self.attr['plugin'] = 'generic'
            plugin_name = 'generic'

        logging.info("Running plugins for %s", self['name'])
        plugin = Node.find_plugin(plugin_name)
        logging.info("Found plugin for node")

        # Check to see if this node has an alias in the nodemap
        try:
            alias = self.node_alias(self['name'])
        except KeyError:
            alias = none

        try:
            plugin.set_node_attrs(self, alias=alias)
        except Exception as E:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            while exc_tb.tb_next != None:
                exc_tb = exc_tb.tb_next 
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logging.error("Plugin caught exception: %s. %s:%d", repr(E), fname, exc_tb.tb_lineno)

    @classmethod
    def load_functions(cls):
        if cls.loaded_functions:
            return
        logging.info("Loading Jinja templates")
        cls.environment = Environment()
        cls.environment.globals['ipadd'] = Network.ipadd
        cls.environment.globals['data'] = Data.data
        cls.environment.globals['nodeset_offset'] = Node.nodeset_offset
        #Environment.globals['ipadd'] = Node.ipadd
        cls.loaded_functions = True

    def interpolatevalue(self, value):
        logging.debug("Interpolating value %s" % value)
        #return str(Template(value).render(**self.attr))
        output = str(Node.environment.from_string(value).render(**self.attr))
        logging.debug("Interpolated value %s as %s", value, output)
        return output
        
    def interpolate(self, key=None, source=None, dest=None):
        """ Interpolates a value from source dict to dest dict.
            Key of None means interpolate all keys in the dict.
            Defaults to interpolating from the Node rawattr to attr
        """
        logging.debug("Interpolating %s", key)
        if not Node.loaded_functions:
            Node.load_functions()
        if source is None:
            source = self.rawattr
        if dest is None:
            dest = self.attr
        if key is None:
            # Interpolate everything in this dict
            for newkey in list(source.keys()):
                self.interpolate(newkey, source, dest)
            return
        if source is self.rawattr:
            Node.environment.globals['offset'] = self.rawattr_nodeset_index[key]
        if isinstance(source[key], dict):
            newdest = dict()
            # This is a hierarchial value, recursively interpolate
            self.interpolate(None, source=source[key], dest=newdest)
            dest[key] = newdest
            del source[key]
        elif isinstance(source[key], list):
            newdest = list()
            for item in source[key]:
                newdest.append(self.interpolatevalue(item))
            dest[key] = newdest
            del source[key]
        elif type(source[key]) == str:
            # Just interpolate one key in the dict
            dest[key] = self.interpolatevalue(source[key])
            del source[key]
        elif type(source[key]) == bool:
            dest[key] = source[key]
            del source[key]
        elif type(source[key]) == int:
            dest[key] = source[key]
            del source[key]
        elif type(source[key]) == types.LambdaType:
            dest[key] = source[key]()
            del source[key]
        else:
            logging.error("Unhandled interpolation for key %s %s", key, type(source[key]))
        del Node.environment.globals['offset']

    @classmethod
    def nodeset_offset(cls, nodesetstr, offset=0):
        logging.debug("Called nodeset_offset with %s, offset %d", nodesetstr, offset)
        if nodesetstr not in cls.nodeset_cache:
            cls.nodeset_cache[nodesetstr] = list(NodeSet(nodesetstr))
            cls.nodeset_cache[nodesetstr].sort()
        ns = cls.nodeset_cache[nodesetstr]
        return ns[offset]
