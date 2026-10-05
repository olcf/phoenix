#!/usr/bin/env python3
"""Phoenix filesync support"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import phoenix
import os
import re
from pathlib import Path
from phoenix.node import Node
from phoenix.system import System

filepattern = re.compile(r'^[\w\-\.\/]+$')

class FileSyncConfigError(Exception):
    """Raised when FileSync configuration is incorrect"""

def get_sync_base():
    return Path(System.setting('filesync', default='/var/opt/phoenix/filesync'))

class FileObject(object):
    def __init__(self, **kwargs):
        self.src = kwargs.get('src', None)
        self.dst = kwargs.get('dst', None)
        self.chown = kwargs.get('chown', None)
        self.chmod = kwargs.get('chmod', None)
        self.content = kwargs.get('content', None)
        self.template = kwargs.get('template', None)

        if self.src is not None and not self._validpath(self.src):
            raise ValueError('src %s may be invalid' % self.src)
        if self.dst is not None and not self._validpath(self.dst):
            raise ValueError('dst %s may be invalid' % self.dst)

        # Relative src paths mean use the Phoenix filesync base, directories only
        if self.src is not None and not Path(self.src).is_absolute():
            if self.dst is not None and self.dst != '/':
                logging.error('Relative filesync entry %s must not have a dst', self.dst)
                raise ValueError
            newsrc = get_sync_base() / self.src
            if not newsrc.is_dir():
                logging.error('Relative filesync entry %s must be a directory', self.src)
                raise ValueError
            self.src = f"{newsrc}/"
            self.dst = '/'
        elif self.dst is None:
            self.dst = self.src

    @classmethod
    def _validpath(cls, path):
        return bool(filepattern.match(path))

    @classmethod
    def has_jinja(cls, text):
        if text is None or not isinstance(text, str):
            return False

        jinja_pattern = r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?\#\}"
        return bool(re.search(jinja_pattern, text))

    def render_content(self, node=None):
        if self.has_jinja(self.content):
            raise NotImplementedError
        return self.content

    def render_template(self, node=None):
        raise NotImplementedError

class Filesync(object):
    filesynctype = "unknown"

    @classmethod
    def queue_node_sync(cls, nodename, client, args):
        if isinstance(nodename, Node):
            node = nodename
            nodename = node['name']
        else:
            node = Node.find_node(nodename)
        if 'filesync' not in node:
            logging.error('filesync is not set for %s', nodename)
            return
        if not isinstance(node['filesync'], list):
            logging.error('Node %s "filesync" attribute must be a list')
            return

        fileobjectlist = list()
        for entry in node['filesync']:
            if isinstance(entry, dict):
                fileobjectlist.append(FileObject(**entry))
            else:
                fileobjectlist.append(FileObject(src=entry))

        ok, message = cls.node_sync(nodename, fileobjectlist, task=None)
        client.output(message)
        return 0 if ok else 1

    @classmethod
    def node_sync(cls, nodename, fileobjectlist, task=None):
        raise NotImplementedError

def find_provider(node):
    try:
        provider = node['filesync_client']
    except KeyError:
        provider = DEFAULT_PROVIDER
    return provider

def find_class(node, provider=None):
    if provider is None:
        provider = find_provider(node)
    return phoenix.get_component('filesync', provider)

DEFAULT_PROVIDER='rsync'
