#!/usr/bin/env python3
"""Generate various config files"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import os
import sys
import logging
import argparse
import socket
import errno

from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

from ClusterShell.NodeSet import NodeSet
import phoenix
import phoenix.parallel
from phoenix.system import System
from phoenix.command import Command
from phoenix.node import Node
from phoenix.bootloader import write_bootloader_scripts

class ConfCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="Generate configuration data")
        parser.add_argument('nodes', default=None, type=str, help='Nodes to generate configuration for')
        subparsers = parser.add_subparsers(help='sub-command help', dest='action')
        parser_hosts = subparsers.add_parser('hosts', help='hosts help')
        parser_hosts.add_argument('--interface', '-i', default=[], type=str, action='append', dest='interfaces', help='Interface to include (default: show all)')
        parser_hosts.add_argument('--network', '-n', default=[], type=str, action='append', dest='networks', help='Networks to include (default: show all)')
        parser_hosts.add_argument('--primary', '-p', default=None, type=str, dest='primary', help='Primary interface to use for the hostname')
        parser_ips = subparsers.add_parser('ips', help='ip help')
        parser_ips.add_argument('--sort', '-s', default=None, type=str, dest='sort', help='Field to sort by')
        parser_dhcp = subparsers.add_parser('dhcp', help='dhcp help')
        parser_updatedhcp = subparsers.add_parser('updatedhcp', help='update dhcp help')
        parser_bootfile = subparsers.add_parser('bootfiles', help='bootfile help')
        parser_ethers = subparsers.add_parser('ethers', help='ethers help')
        parser_ethers.add_argument('--interface', '-i', default=[], type=str, action='append', dest='interfaces', help='Interface to include (default: show all)')
        parser_slingshot = subparsers.add_parser('slingshot', help='slingshot help')
        parser_slingshot.add_argument('--interface', '-i', default=[], type=str, action='append', dest='interfaces', help='Interface to include (default: show all)')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        phoenix.parallel.parser_add_arguments_parallel(parser)
        return parser

    @classmethod
    def cli(cls):
        parser = cls.get_parser()
        args = parser.parse_args()

        phoenix.setup_logging(args.verbose)
        nodes = NodeSet(args.nodes)

        cmdmap = { 'hosts':      cls.hosts,
                   'ips':        cls.ips,
                   'bootfiles':  cls.bootfiles,
                   'ethers':     cls.ethers,
                   'dhcp':       cls.dhcp,
                   'updatedhcp': cls.updatedhcp,
                   'slingshot':  cls.slingshot,
                 }

        if args.action in cmdmap:
            rc = cmdmap[args.action](nodes, args)
        else:
            logging.error("Action %s not yet implemented", args.action)
            return 1
        return rc

    @classmethod
    def hosts(cls, nodes, args):
        System.load_config()
        Node.load_nodes(nodeset=nodes)
        for nodename in nodes:
            node = Node.find_node(nodename)
            if 'interfaces' not in node:
                continue
            for ifacename in sorted(node['interfaces']):
                iface = node['interfaces'][ifacename]
                if len(args.interfaces) > 0 and ifacename not in args.interfaces:
                    continue
                if len(args.networks) > 0 and ('network' not in iface or iface['network'] not in args.networks):
                    continue
                if 'ip' not in iface:
                    continue
                components = [iface['ip']]
                if 'hostname' in iface:
                    hostname = iface['hostname']
                    components.append('%s.%s' % (hostname, System.config['domain']))
                    components.append(hostname)
                elif ifacename == args.primary:
                    hostname = nodename
                    components.append('%s.%s' % (hostname, System.config['domain']))
                    components.append(hostname)
                    hostname = "%s-%s" % (nodename, ifacename)
                    components.append('%s.%s' % (hostname, System.config['domain']))
                    components.append(hostname)
                    if 'alias' in iface:
                        components.append(iface['alias'])
                else:
                    hostname = "%s-%s" % (nodename, ifacename)
                    components.append('%s.%s' % (hostname, System.config['domain']))
                    components.append(hostname)
                    if 'alias' in iface:
                        components.append(iface['alias'])
                        components.append("%s-%s" % (iface['alias'], ifacename))
                print("\t".join(components))
        return 0

    @classmethod
    def _sort_ips(cls, thing):
        if cls.interface_sort is None:
            return thing
        elif cls.interface_sort in thing[1]:
            ip_str = thing[1][cls.interface_sort]
            try:
                ip_bytes = socket.inet_aton(ip_str)
                return (ip_bytes, thing)
            except socket.error:
                return (b'', thing)
        return (b'', thing)

    @classmethod
    def ips(cls, nodes, args):
        red = '\033[1;31m'
        end = '\033[0;0m'
        System.load_config()
        Node.load_nodes(nodeset=nodes)
        data = dict()
        ips = dict()
        dupes = dict()
        for nodename in nodes:
            node = Node.find_node(nodename)
            if 'interfaces' not in node:
                continue
            nettoipmap = dict()
            for iface in node['interfaces']:
                if 'ip' not in node['interfaces'][iface]:
                    continue
                if 'network' in node['interfaces'][iface]:
                    key = node['interfaces'][iface]['network']
                else:
                    key = iface
                ip = node['interfaces'][iface]['ip']
                if iface == "bmc" and (node['interfaces']['bmc']['network'] in [node['interfaces'][if2]['network'] for if2 in node['interfaces'] if if2 != "bmc"]):
                    data[node['name'] + "-bmc"] = { key: ip }
                elif iface == "bond0.float" and (node['interfaces']['bond0.float']['network'] in [node['interfaces'][if2]['network'] for if2 in node['interfaces'] if if2 != "bond0.floar"]):
                    data[node['name'] + "-float"] = { key: ip }
                else:
                    nettoipmap[key] = ip
                # Check to see if this IP is a duplicate
                if ip in ips:
                    dupes[ip] = True
                    logging.error("Duplicate IP %s", ip)
                ips[ip] = True
            data[node['name']] = nettoipmap
        networks = list(set([network for item in data.values() for network in item.keys()]))
        cols = ["Node"] + networks
        cls.interface_sort = networks[0]
        if 'sort' in args and args.sort is not None:
            if args.sort == "name" or args.sort == "node":
                cls.interface_sort = None
            else:
                if args.sort in networks:
                    cls.interface_sort = args.sort
                else:
                    logging.error("Could not find interface %s to sort by", args.sort)
        print("|%s|" % "|".join(['{:<15}'.format(x) for x in cols]))
        for node, val in sorted(data.items(), key=cls._sort_ips):
            cols = [ (red + '{:<15}'.format(val[network]) + end if val[network] in dupes else '{:<15}'.format(val[network])) if network in val else '{:<15}'.format("<None>") for network in networks ]
            cols.insert(0, '{:<15}'.format(node))
            print("|%s|" % "|".join(cols))

        return 0

    @classmethod
    def bootfiles(cls, nodes, args):
        Node.load_nodes(nodeset=nodes)
        write_bootloader_scripts()
        return 0

    @classmethod
    def ethers(cls, nodes, args):
        System.load_config()
        Node.load_nodes(nodeset=nodes)
        for nodename in nodes:
            node = Node.find_node(nodename)
            if 'interfaces' not in node:
                continue
            for ifacename, iface in node['interfaces'].items():
                if len(args.interfaces) > 0 and ifacename not in args.interfaces:
                    continue
                if 'mac' not in iface:
                    continue
                ip = iface['ip']
                print("%s\t%s" % (iface['mac'], ip))

        return 0

    @classmethod
    def slingshot(cls, nodes, args):
        System.load_config()
        Node.load_nodes(nodeset=nodes)
        for nodename in nodes:
            node = Node.find_node(nodename)
            if 'interfaces' not in node:
                continue
            for ifacename, iface in node['interfaces'].items():
                if len(args.interfaces) > 0 and ifacename not in args.interfaces:
                    continue
                if 'mac' not in iface:
                    continue
                if 'nid' not in iface:
                    continue
                ip = iface['ip']
                print("%s-%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d" % (node['name'], ifacename, iface['nid'], iface['mac'], ip, iface['switch'], iface['group'], iface['switchnum'], iface['port']))

        return 0

    @classmethod
    def dhcp(cls, nodes, args):
        System.load_config()
        # NOTE: it doesn't really make sense to include a nodeset here...
        Node.load_nodes()
        provider = load_dhcp_provider()
        print(provider.get_dhcp_conf())
        return 0

    @classmethod
    def updatedhcp(cls, nodes, args):
        System.load_config()
        # NOTE: it doesn't really make sense to include a nodeset here...
        Node.load_nodes()
        provider = load_dhcp_provider()
        print(provider.update_dhcp_reservations())
        return 0

    @classmethod
    def run(cls, client):
        ''' Run the action for a single host (this is one instance of a parallel request '''
        action = client.command[1]
        client.output("Not yet implemented", stderr=True)
        return 1

if __name__ == '__main__':
    sys.exit(ConfCommand.run())
