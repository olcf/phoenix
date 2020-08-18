#!/usr/bin/env python
"""Phoenix bootloader support"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import Phoenix
from Phoenix.Node import Node
import socket
import fcntl
import os
import signal

try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    class BaseHTTPRequestHandler(object):
        def __init__(self):
            logging.error("Could not find BaseHTTPRequestHandler, install the python package")
            sys.exit(1)

need_to_reload = False

def handler(signum, frame):
    global need_to_reload
    need_to_reload = True

class BootfileServer(object):
    def __init__(self, port=8000, require_privports=False):
        self.port = port
        self.require_privports = require_privports
        signal.signal(signal.SIGIO, handler)
        fd = os.open(Phoenix.conf_path, os.O_RDONLY)
        fcntl.fcntl(fd, fcntl.F_SETSIG, 0)
        fcntl.fcntl(fd, fcntl.F_NOTIFY, fcntl.DN_MODIFY | fcntl.DN_CREATE | fcntl.DN_MULTISHOT)

    def serve_forever(self):
        try:
            httpd = HTTPServer(('0.0.0.0', self.port), PhoenixBootfileHandler)
        except NameError:
            logging.error("Could not find HTTPServer, install the python package")
            sys.exit(1)
        httpd.require_privports = self.require_privports
        httpd.serve_forever()

class PhoenixBootfileHandler(BaseHTTPRequestHandler):
    def return404(self):
        self.send_response(404)
        self.end_headers()
        self.wfile.write('Node not found')

    def do_GET(self):
        global need_to_reload
        if need_to_reload:
            logging.info('Detected config changes - reloading')
            Node.load_nodes(clear=True)
            need_to_reload = False

        if self.server.require_privports and self.client_address[1] > 1024:
            logging.error("Denying unauthenticated request from %s:%s", self.client_address[0], self.client_address[1])
            self.send_response(403)
            self.end_headers()
            self.wfile.write('Access denied')
            return

        try:
            hostname, aliases, _ = socket.gethostbyaddr(self.client_address[0])
        except OSError:
            self.return404()
            return

        node = None
        try:
            node = Node.find_node(hostname)
        except KeyError:
            for alias in aliases:
                try:
                    node = Node.find_node(alias)
                    break
                except KeyError:
                    pass

        if node == None:
            self.return404()
            return

        loader_class = _find_class(node)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(loader_class.script(node))

def get_bootloader_script(node):
    loader_class = _find_class(node)
    return loader_class.script(node)

def write_bootloader_scripts():
    for nodename,node in sorted(Node.nodes.items()):
	if 'interfaces' in node:
	    for ifacename, iface in node['interfaces'].items():
		with open ('%s/bootfiles/%s' % (Phoenix.artifact_path, iface['ip']), 'w') as ofile:
		    ofile.write(get_bootloader_script(node))

def _find_class(node):
    try:
        loader = node['bootloader']
    except KeyError:
        loader = 'ipxe'

    classname = loader.lower().capitalize()
    modname = "Phoenix.BootLoader.%s" % classname

    # Iterate over a copy of sys.modules' keys to avoid RuntimeError
    if modname.lower() not in [mod.lower() for mod in list(sys.modules)]:
        # Import module if not yet loaded
        __import__(modname)

    # Get the class pointer
    try:
        return getattr(sys.modules[modname], classname)
    except:
        raise ImportError("Could not find class %s" % classname)

class BootLoader(object):
    bootloadertype = "unknown"
