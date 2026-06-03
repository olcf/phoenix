#!/usr/bin/env python3
"""Phoenix bootloader support"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import phoenix
from phoenix.node import Node
import os
from pathlib import Path

def get_bootloader_script(node, interface=None, provider=None):
    loader_class = _find_class(node, provider)
    return loader_class.script(node, interface=interface)

def write_bootloader_scripts():
    bldir = Path(phoenix.artifact_path) / 'bootfiles'
    if not bldir.is_dir():
        bldir.mkdir()
    for nodename,node in sorted(Node.nodes.items()):
        if 'interfaces' in node:
            for ifacename, iface in node['interfaces'].items():
                if ifacename == 'bmc':
                    continue
                if 'dhcp' not in iface or iface['dhcp'] == False:
                    logging.debug("Skipping %s %s because it is not set for DHCP", node['name'], ifacename)
                    continue
                try:
                    provider = _find_provider(node)
                    script = get_bootloader_script(node, interface=ifacename, provider=provider)
                except Exception as e:
                    logging.debug("Skipping %s %s because a script was not generated (%s)", node['name'], ifacename, e)
                    continue
                provdir = bldir / provider
                if not provdir.is_dir():
                    provdir.mkdir()
                outputpath = provdir / iface['ip']
                logging.debug("Writing bootfile to %s", outputpath)
                with open (outputpath, 'w') as ofile:
                    ofile.write(script)

def _find_provider(node):
    try:
        provider = node['bootloader']
    except KeyError:
        provider = DEFAULT_PROVIDER
    return provider

def _find_class(node, provider=None):
    if provider is None:
        provider = _find_provider(node)
    return phoenix.get_component('bootloader', provider)

class Bootloader(object):
    bootloadertype = "unknown"

DEFAULT_PROVIDER='ipxe'
