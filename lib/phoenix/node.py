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
from jinja2.runtime import Context
import re
import copy
import importlib
import ipaddress
import collections
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

class NodeLayerMeta(object):
    def __init__(self, layertype=None, file=None, line=None, noderange=None, nodeset=None):
        self.layertype = layertype
        self.file = file
        self.line = line
        self.noderange = noderange
        self.nodeset = nodeset

class NodeLayer(object):
    def __init__(self, meta=None, layertype=None, file=None, line=None, noderange=None, nodeset=None, data=None):
        if meta is None:
            self.meta = NodeLayerMeta(layertype = layertype,
                                      file = file,
                                      line = line,
                                      noderange = noderange,
                                      nodeset = nodeset)
        else:
            self.meta = meta
        self.data = data or {}

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data[key]

    def __str__(self):
        return str(self.data)

    def __repr__(self):
        return str(self.data)

    def __iter__(self):
        return iter(self.data)

class NodeLayerMap(collections.abc.Mapping):
    def __init__(self, node=None, initlayers=None):
        self.node = node
        self.layers = initlayers or []
        self.layers.insert(0, NodeLayer(layertype="cache"))

    def addlayer(self, layer, position=None):
        ''' Adds a layer to the map at the desired position. Position must be
            after the cache layer (cache always wins).
        '''
        if position is None:
            position = 1
        elif position < 1:
            raise IndexError
        self.layers.insert(position, layer)

    def haslayeroftype(self, layertype):
        ''' Determines if any of this map's layers are of the specified type'''
        for layer in self.layers:
            if layer.meta.layertype == layertype:
                return True
        return False

    def __str__(self):
        return(str(dict(self)))

    def __repr__(self):
        return(str(dict(self)))

    def getsubmapping(self, key):
        return NodeLayerMap(self.node, [NodeLayer(meta=layer.meta, data=layer.data[key]) for layer in self.layers if key in layer.data and isinstance(layer.data[key], collections.abc.Mapping)])

    def __getitem__(self, key):
        for layer in self.layers:
            try:
                result = layer.data[key]
                if isinstance(result, collections.abc.Mapping):
                    return self.getsubmapping(key)
                elif isinstance(result, NodeTemplate):
                    return result.render(self.node)
                else:
                    return result
            except KeyError:
                pass
        raise KeyError(key)

    def getwithblame(self, key):
        for layer in self.layers:
            try:
                result = layer.data['key']
                blame = layer.meta
                return (result, blame)
            except KeyError:
                pass
        raise KeyError(key)

    def __contains__(self, key):
        return any(key in l.data for l in self.layers)

    def __iter__(self):
        return iter(set().union(*self.layers))

    def __setitem__(self, key, value):
        if self.node.in_plugin:
            # Add to plugin layer
            self.layers[-1].data[key] = value
        else:
            # Add to cache layer
            self.layers[0].data[key] = value

    def __len__(self):
        return len(set().union(*self.layers))

class NodeContext(Context):
    def resolve_or_missing(self, key):
        logging.debug("Inside NodeContext resolve_or_missing")
        if 'node' in self.parent and key in self.parent['node']:
            return self.parent['node'][key]
        return super().resolve_or_missing(key)

class NodeTemplate(object):
    def __init__(self, templatestr):
        self.template = Node.environment.from_string(templatestr)
        self.templatestr = templatestr

    def render(self, node):
        return self.template.render({'node':node})

    def __str__(self):
        return "<unrendered template: %s>" % self.templatestr

    def __repr__(self):
        return "<unrendered template: %s>" % self.templatestr

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
        self.ran_plugins = False
        self.in_plugin = False
        self.linked_model = False
        self.name = name
        self.data = NodeLayerMap(self)
        self['name'] = name

    def __repr__(self):
        if not self.ran_plugins:
            self.run_plugins()
        if not self.linked_model:
            self.link_model()
        return yaml.dump({self.name: dict(self.data)}, default_flow_style=False)

    def setrawitem(self, key, value):
        self.data[key] = value

    def setifblank(self, key, value):
        if key not in self:
            self.data[key] = value

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        if key == "name":
            return self.name
        if not self.ran_plugins:
            self.run_plugins()
        if not self.linked_model:
            self.link_model()
        try:
            result = self.data[key]
            return result
        except:
            raise
        if 'model' in self.attr and self.attr['model'] in Node.models:
            if key in Node.models[self.attr['model']]:
                return Node.models[self.attr['model']][key]
        raise KeyError("Node %s does not have attribute \"%s\"" % (self.attr['name'], key))

    def __delitem__(self, key):
        raise NotImplementedError("Attributes cannot be deleted from a node")

    def __contains__(self, key):
        return key in self.data

    def addlayer(self, layer, position=None):
        self.data.addlayer(layer, position)

    @classmethod
    def load_nodes(cls, filename=None, datastr=None, nodeset=None, clear=False):
        """ Reads and processes node data.
            Can be called more than once to load multiple files,
            or if you want to focus on a different nodeset. By
            default, it just adds to the current view of nodes.
            Set clear=True to clear all currently-known nodes.
        """

        # Clear known nodes if requested
        if clear:
            cls.nodes = dict()

        if filename is not None and datastr is not None:
            logging.error("Cannot load nodes from a file and string")
            return False
        elif filename is None and datastr is None:
            filename = "%s/nodes.yaml" % phoenix.conf_path

        if filename is not None:
            logging.info("Loading node file '%s'", filename)
            with open(filename) as nodefd:
                nodedata = yaml.load(nodefd, Loader=Loader) or {}
        elif datastr is not None:
            filename = 'datastr'
            nodedata = yaml.load(datastr, Loader=Loader) or {}

        # Load the data into the node structures
        for noderange, data in nodedata.items():
            ns1 = NodeSet(noderange)

            # Convert any value using Jinja2 to a compiled template
            Node.create_templates(data)

            newlayer = NodeLayer(layertype='normal',
                                 file=filename,
                                 noderange=noderange,
                                 nodeset=ns1,
                                 data=data
                                )

            for node_nodeset_index, node in enumerate(ns1):
                # Optimization to skip nodes we don't care about
                if nodeset is not None and node not in nodeset:
                    continue
                if node not in cls.nodes:
                    cls.nodes[node] = Node(node)

                # Add the layer to the node
                cls.nodes[node].addlayer(newlayer)

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

        if 'plugin' in self:
            plugin_name = self['plugin']
        else:
            self['plugin'] = 'generic'
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
            self.in_plugin = True
            plugin_layer = NodeLayer(layertype='nodeplugin')
            self.addlayer(plugin_layer, position=999)
            plugin.set_node_attrs(self, layer=plugin_layer, alias=alias)
            self.in_plugin = False
        except Exception as E:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            while exc_tb.tb_next != None:
                exc_tb = exc_tb.tb_next 
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logging.error("Plugin caught exception: %s. %s:%d", repr(E), fname, exc_tb.tb_lineno)
            raise

    def link_model(self):
        if self.linked_model:
            return
        self.linked_model = True

        if 'model' in self:
            if 'model' in self.models:
                self.addlayer(self.models[self['model']], 999)

    @classmethod
    def load_functions(cls):
        if cls.loaded_functions:
            return
        logging.info("Loading Jinja templates")
        cls.environment = Environment()
        cls.environment.context_class = NodeContext
        cls.environment.globals['ipadd'] = Network.ipadd
        cls.environment.globals['data'] = Data.data
        cls.environment.globals['nodeset_offset'] = Node.nodeset_offset
        #Environment.globals['ipadd'] = Node.ipadd
        cls.loaded_functions = True

    @classmethod
    def nodeset_offset(cls, nodesetstr, offset=0):
        logging.debug("Called nodeset_offset with %s, offset %d", nodesetstr, offset)
        if nodesetstr not in cls.nodeset_cache:
            cls.nodeset_cache[nodesetstr] = list(NodeSet(nodesetstr))
            cls.nodeset_cache[nodesetstr].sort()
        ns = cls.nodeset_cache[nodesetstr]
        return ns[offset]

    @classmethod
    def create_templates(cls, data):
        ''' Searches a data structure for any template strings and converts them
            Assume this is called for a dict
            Returns True if a template was created, false otherwise
        '''
        logging.debug("Calling create_templates")
        has_templates = False
        if not cls.loaded_functions:
            cls.load_functions()

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    if Node.create_templates(value):
                        has_templates = True
                elif isinstance(value, str) and cls.tpl_regex.search(value):
                    data[key] = NodeTemplate(value)
                    has_templates = True
        elif isinstance(data, list):
            for index, value in enumerate(data):
                if isinstance(value, str) and cls.tpl_regex.search(value):
                    data[index] = NodeTemplate(value)
                    has_templates = True
        return has_templates

# How to represent a Node in yaml
def node_representer(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map', data)
def nodelayermap_representer(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map', data)
def nodetemplate_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', str(data))

# Register the representer
#yaml.add_representer(Node, node_representer)
yaml.add_representer(NodeLayerMap, nodelayermap_representer)
yaml.add_representer(NodeTemplate, nodetemplate_representer)
