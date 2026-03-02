#!/usr/bin/env python3
"""Phoenix bootloader support for iPXE"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
from phoenix.bootloader import Bootloader
from phoenix.node import Node
import jinja2
from jinja2 import Template

ipxe_template = """
{%- set server = 'http://' + http_server | default('${dhcp-server}') + ':' + http_server_port | default('8000')  -%}
{%- if kcmdline is iterable and kcmdline is not string %}
{%- set kcmdline = kcmdline | join(" ") -%}
{%- endif -%}
#!ipxe
kernel {{server}}/images/{{image}}/vmlinuz initrd=initramfs.img root=live:{{server}}/images/{{image}}/rootdir.squashfs BOOTIF=${mac} ip=dhcp console={{console|default('ttyS0,115200')}} {{kcmdline}} || goto failed
initrd {{server}}/images/{{image}}/initramfs.img || goto failed
boot || goto failed

:failed
echo
echo Boot must have failed
echo
echo Sleeping 30 seconds
echo
sleep 30
echo Restarting networking
ifclose
ifconf
echo
chain {{server}}/bootfile

"""

class IpxeBootloader(Bootloader):
    bootloadertype = 'ipxe'
    def_template = Node.environment.from_string(ipxe_template)

    @classmethod
    def script(cls, node):
        logging.debug("Generating iPXE script for node %s", node['name'])

        if 'image' not in node:
            raise KeyError('No image set for %s, not generating bootfile' % node['name'])

        script = cls.def_template.render({'node': node})
        return script
