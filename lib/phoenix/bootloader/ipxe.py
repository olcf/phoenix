#!/usr/bin/env python3
"""Phoenix bootloader support for iPXE"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
from phoenix.bootloader import Bootloader

class IpxeBootloader(Bootloader):
    bootloadertype = 'ipxe'

    @classmethod
    def script(cls, node):
        logging.debug("Generating iPXE script for node %s", node['name'])

        try:
            image = node['image']
        except KeyError:
            logging.warn('No image set for %s, not generating bootfile', node['name'])
            raise

        try:
            server_ip = node['http_server']
        except KeyError:
            server_ip = '${dhcp-server}'

        try:
            server_port = node['http_server_port']
        except KeyError:
            server_port = 8000

        try:
            console = node['console']
        except KeyError:
            console = 'ttyS0,115200'

        try:
            kcmdline = node['kcmdline']
        except KeyError:
            kcmdline = ''

        default_args = "BOOTIF=${mac} ip=${ip}:%s-%d:${gateway}:${netmask}:${hostname} rw" % (server_ip, server_port)

        result = list()
        result.append('#!ipxe')
        result.append('kernel http://%s:%d/images/%s/vmlinuz initrd=initramfs.gz %s console=%s %s' %
                            (server_ip, server_port, node['image'], default_args, console, kcmdline))
        result.append('initrd http://%s:%d/images/%s/initramfs.gz' % (server_ip, server_port, node['image']))
        result.append('boot ||')
        result.append('echo')
        result.append('echo Boot must have failed')
        result.append('echo')
        result.append('echo Sleeping 30 seconds')
        result.append('sleep 30')
        result.append('chain http://%s:%d/bootfile' % (server_ip, server_port))
        result.append('')

        return '\n'.join(result)
