#!/usr/bin/env python
"""Power management"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import argparse

from ClusterShell.NodeSet import NodeSet
import phoenix
import phoenix.parallel
from phoenix.system import System
from phoenix.command import Command
from phoenix.node import Node
from phoenix.bootloader import write_bootloader_scripts

def appendraw(val, hpcmattr, node, thelist):
    thelist.append("{}={}".format(hpcmattr, val))

def appendattr(nodeattr, hpcmattr, node, thelist, thedefault=None):
    if nodeattr in node:
        thelist.append("{}={}".format(hpcmattr, node[nodeattr]))
    elif thedefault != None:
        thelist.append("{}={}".format(hpcmattr, thedefault))

def appendifaceattr(interface, ifaceattr, hpcmattr, node, thelist):
    try:
        thelist.append("{}={}".format(hpcmattr, node['interfaces'][interface][ifaceattr]))
    except KeyError:
        pass

class ConfCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="Generate configuration data")
        parser.add_argument('nodes', default=None, type=str, help='Nodes to generate configuration for')
        subparsers = parser.add_subparsers(help='sub-command help', dest='action')
        parser_hosts = subparsers.add_parser('hosts', help='hosts help')
        parser_hosts.add_argument('--interface', '-i', default=[], type=str, action='append', dest='interfaces', help='Interface to include (default: show all)')
        parser_ips = subparsers.add_parser('ips', help='ip help')
        parser_dhcp = subparsers.add_parser('dhcp', help='dhcp help')
        parser_updatedhcp = subparsers.add_parser('updatedhcp', help='update dhcp help')
        parser_bootfile = subparsers.add_parser('bootfiles', help='bootfile help')
        parser_ethers = subparsers.add_parser('ethers', help='ethers help')
        parser_ethers.add_argument('--interface', '-i', default=[], type=str, action='append', dest='interfaces', help='Interface to include (default: show all)')
        parser_hpcm = subparsers.add_parser('hpcm', help='hpcm help')
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
                   'hpcm':       cls.hpcm
                 }

        if args.action in cmdmap:
            rc = cmdmap[args.action](nodes, args)
        else:
            logging.error("Action %s not yet implemented", args.action)
            return 1
        return rc

        (task, handler) = phoenix.parallel.setup(nodes, args)
        cmd = ["power", args.action]
        if args.pdu:
            cmd.append("pdu")
        logging.debug("Submitting shell command %s", cmd)
        task.shell(cmd, nodes=nodes, handler=handler, autoclose=False, stdin=False, tree=True, remote=False)
        task.resume()
        rc = 0
        return rc

    @classmethod
    def hosts(cls, nodes, args):
        System.load_config()
        Node.load_nodes(nodeset=nodes)
        for nodename in nodes:
            node = Node.find_node(nodename)
            if 'interfaces' not in node:
                continue
            for ifacename, iface in node['interfaces'].items():
                if len(args.interfaces) > 0 and ifacename not in args.interfaces:
                    continue
                if 'ip' not in iface:
                    continue
                hostname = iface['hostname'] if 'hostname' in iface else nodename
                print "%s\t%s\t%s.%s" % (iface['ip'], hostname, hostname, System.config['domain'])
        return 0

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
            data[node['name']] = { iface: node['interfaces'][iface]['ip'] for iface in node['interfaces'] if 'ip' in node['interfaces'][iface]}
            for ip in data[node['name']].values():
                if ip in ips:
                    dupes[ip] = True
                    logging.error("Duplicate IP %s", ip)
                ips[ip] = True
        interfaces = list(set([ item.keys() for name,item in data.items() ][0]))
        cols = ["Node"] + interfaces
        print("|%s|" % "|".join(['{:<15}'.format(x) for x in cols]))
        for node, val in sorted(data.items()):
            cols = [ (red + val[interface] + end if val[interface] in dupes else val[interface]) if interface in val else "<None>" for interface in interfaces ]
            cols.insert(0, node)
            print("|%s|" % "|".join(['{:<15}'.format(x) for x in cols]))

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
                hostname = iface['hostname'] if 'hostname' in iface else nodename
                print "%s\t%s" % (iface['mac'], hostname)

        return 0

    @classmethod
    def dhcp(cls, nodes, args):
        System.load_config()
        # NOTE: it doesn't really make sense to include a nodeset here...
        Node.load_nodes()
        provider = load_dhcp_provider()
        print provider.get_dhcp_conf()
        return 0

    @classmethod
    def updatedhcp(cls, nodes, args):
        System.load_config()
        # NOTE: it doesn't really make sense to include a nodeset here...
        Node.load_nodes()
        provider = load_dhcp_provider()
        print provider.update_dhcp_reservations()
        return 0

    @classmethod
    def hpcm(cls, nodes, args):
        System.load_config()
        Node.load_nodes(nodeset=nodes)
        print("[discover]")
        for nodename in nodes:
            n = Node.find_node(nodename)
            it = list()
            appendattr('name', 'hostname1', n, it)
            if n['plugin'] == 'cray_ex' and n['type'] == 'nc':
                print("internal_name={name},hostname1={name},mgmt_bmc_net_macs=\"{mac}\",mgmt_bmc_net_name=hostctrl3000,rack_nr={rack},chassis={chassis},tray={slot},cmm_parent={pdu},username=root,password=initial0,node_controller".format(name=n['name'], mac=n['interfaces']['me0']['mac'], rack=n['racknum'], chassis=n['chassis'], slot=n['slot'], pdu=n['pdu']))
            elif n['plugin'] == 'cray_ex' and n['type'] == 'compute':
                servicenum = 1000 + n['nodeindex']
                print("internal_name=service{servicenum},mgmt_net_macs=\"{mac}\",mgmt_net_name=hostmgmt2000,rack_nr={rack},chassis={chassis},tray={slot},node_nr={nodenum},controller_nr={board},hostname1={name},node_controller={bmc},network_group=rack{rack},console_device=ttyS0,conserver_logging=yes,rootfs=nfs,nfs_writable_type=tmpfs-overlay,transport=rsync,mgmt_net_bonding_master=bond0,dhcp_bootfile=ipxe-direct,mgmt_net_interfaces=\"enp65s0\",baud_rate=115200,image={image}".format(name=n['name'], mac=n['interfaces']['eth0']['mac'], rack=n['racknum'], chassis=n['chassis'], slot=n['slot'], board=n['board'], nodenum=n['nodenum'], bmc=n['bmc'], servicenum=servicenum, image=n['image']))
            elif n['plugin'] == 'cray_ex' and n['type'] == 'switch':
                appendraw(n['name'], 'internal_name', n, it)
                appendraw('head-bmc', 'mgmt_bmc_net_name', n, it)
                appendifaceattr('eth0', 'mac', 'mgmt_bmc_net_macs', n, it)
                appendifaceattr('eth0', 'ip', 'mgmt_bmc_net_ip', n, it)
                appendraw('root', 'username', n, it)
                appendraw('initial0', 'password', n, it)
                it.append('external_switch_controller')
            else:
                if 'hpcm_servicenum' in n:
                    servicenum = n['hpcm_servicenum']
                elif 'type' in n:
                    if n['type'] == 'admin':
                        servicenum = 100 + n['nodeindex']
                    elif n['type'] == 'leader':
                        servicenum = 200 + n['nodeindex']
                    elif n['type'] == 'service':
                        servicenum = 300 + n['nodeindex']
                    elif n['type'] == 'login':
                        servicenum = 400 + n['nodeindex']
                    elif n['type'] == 'gateway':
                        servicenum = 500 + n['nodeindex']
                    elif n['type'] == 'utility':
                        servicenum = 600 + n['nodeindex']
                    elif n['type'] == 'compute':
                        servicenum = 2000 + n['nodeindex']
                    else:
                        servicenum = 700 + n['nodeindex']
                else:
                    servicenum = 800 + n['nodeindex']
                appendraw('service%d' % servicenum, 'internal_name', n, it)
                appendifaceattr('bmc', 'mac', 'mgmt_bmc_net_macs', n, it)
                appendifaceattr('bmc', 'ip', 'mgmt_bmc_net_ip', n, it)
                appendifaceattr('eth0', 'mac', 'mgmt_net_macs', n, it)
                appendifaceattr('eth0', 'ip', 'mgmt_net_ip', n, it)
                appendraw('hsn0', 'data1_net_name', n, it)
                appendraw('hsn0', 'data1_net_interfaces', n, it)
                appendifaceattr('hsn0', 'ip', 'data1_net_ip', n, it)
                appendattr('rootfs', 'rootfs', n, it, 'tmpfs')
                appendattr('arch', 'architecture', n, it, 'x86_64')
                appendattr('image', 'image', n, it)
                #appendattr('bmctype', 'card_type', n, it, 'ILO')
                appendraw('ILO', 'card_type', n, it)
                appendattr('bmcuser', 'bmc_username', n, it, 'root')
                appendattr('bmcpassword', 'bmc_password', n, it)
                appendraw('yes', 'conserver_logging', n, it)
                appendraw('yes', 'predictable_net_names', n, it)
                appendraw('ipxe-direct', 'dhcp_bootfile', n, it)
                appendattr('hpcm_transport', 'transport', n, it, 'rsync')
                appendattr('console', 'console_device', n, it, 'ttyS0')
            print ', '.join(it)
        return 0

    @classmethod
    def run(cls, client):
        ''' Run the action for a single host (this is one instance of a parallel request '''
        action = client.command[1]
        client.output("Not yet implemented", stderr=True)
        return 1

if __name__ == '__main__':
    sys.exit(ConfCommand.run())
