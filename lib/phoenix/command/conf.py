#!/usr/bin/env python
"""Power management"""
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

class ParamList(object):
    def __init__(self, node):
        self.node = node
        self.paramlist = list()

    def addraw(self, hpcmattr, val=None):
        if val is None:
            self.paramlist.append(hpcmattr)
            return
        if ',' in val:
            val = '"{}"'.format(val)
        self.paramlist.append("{}={}".format(hpcmattr, val))

    def addna(self, hpcmattr, nodeattr, thedefault=None):
        if nodeattr in self.node:
            self.paramlist.append("{}={}".format(hpcmattr, self.node[nodeattr]))
        elif thedefault != None:
            self.paramlist.append("{}={}".format(hpcmattr, thedefault))

    def addia(self, hpcmattr, interface, ifaceattr):
        try:
            self.paramlist.append("{}={}".format(hpcmattr, self.node['interfaces'][interface][ifaceattr]))
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
        parser_ips.add_argument('--sort', '-s', default=None, type=str, dest='sort', help='Field to sort by')
        parser_dhcp = subparsers.add_parser('dhcp', help='dhcp help')
        parser_updatedhcp = subparsers.add_parser('updatedhcp', help='update dhcp help')
        parser_bootfile = subparsers.add_parser('bootfiles', help='bootfile help')
        parser_ethers = subparsers.add_parser('ethers', help='ethers help')
        parser_ethers.add_argument('--interface', '-i', default=[], type=str, action='append', dest='interfaces', help='Interface to include (default: show all)')
        parser_hpcm = subparsers.add_parser('hpcm', help='hpcm help')
        subparser_hpcm = parser_hpcm.add_subparsers(help='sub-command help', dest='action2')
        parser_hpcm_discover = subparser_hpcm.add_parser('discover', help='Generate a fastdiscover file')
        parser_hpcm_repos = subparser_hpcm.add_parser('repos', help='Manage HPCM repos and repo groups')
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
    def _sort_ips(cls, thing):
        if cls.interface_sort is None:
            return thing
        elif cls.interface_sort in thing[1]:
            return socket.inet_aton(thing[1][cls.interface_sort])
        return thing

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
        if args.action2 == 'discover':
            cls.hpcm_discover(nodes, args)
        elif args.action2 == 'repos':
            cls.hpcm_repos(nodes, args)

    @classmethod
    def hpcm_discover(cls, nodes, args):
        System.load_config()
        Node.load_nodes(nodeset=nodes)
        print("[discover]")
        for nodename in nodes:
            n = Node.find_node(nodename)
            it = ParamList(n)
            it.addna('hostname1', 'name')
            if n['plugin'] == 'cray_ex' and n['type'] == 'nc':
                print("internal_name={name},hostname1={name},mgmt_bmc_net_macs=\"{mac}\",mgmt_bmc_net_name=hostctrl3000,rack_nr={rack},chassis={chassis},tray={slot},cmm_parent={pdu},username=root,password=initial0,node_controller".format(name=n['name'], mac=n['interfaces']['me0']['mac'], rack=n['racknum'], chassis=n['chassis'], slot=n['slot'], pdu=n['pdu']))
            elif n['plugin'] == 'cray_ex' and n['type'] == 'switch':
                it.addna('internal_name', 'name')
                it.addraw('mgmt_bmc_net_name', 'head-bmc')
                it.addna('mgmt_bmc_net_macs', 'eth0', 'mac')
                it.addna('mgmt_bmc_net_ip', 'eth0', 'ip')
                it.addraw('username', 'root')
                it.addraw('password', 'initial0')
                it.addraw('external_switch_controller')
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
                it.addraw('internal_name', 'service%d' % servicenum)
                cls._add_interfaces(n, it)
                it.addna('rootfs', 'rootfs', 'tmpfs')
                it.addna('architecture', 'arch', 'x86_64')
                it.addna('image', 'image')
                it.addraw('card_type', 'ILO')
                it.addna('bmc_username', 'bmcuser', 'root')
                it.addna('bmc_password', 'bmcpassword', 'initial0')
                it.addraw('conserver_logging', 'yes')
                it.addraw('redundant_mgmt_network', 'yes')
                it.addraw('predictable_net_names', 'yes')
                it.addna('dhcp_bootfile', 'ipxe-direct')
                it.addna('transport', 'hpcm_transport', 'rsync')
                it.addna('console_device', 'console', 'ttyS0')
                if n['plugin'] == 'cray_ex' and n['type'] == 'compute':
                    it.addna('rack_nr', 'racknum')
                    it.addna('chassis', 'chassis')
                    it.addna('tray', 'slot')
                    it.addna('node_nr', 'nodenum')
                    it.addna('controller_nr', 'board')
                    it.addna('node_controller', 'bmc')
                    it.addraw('network_group', "rack%d" % n['racknum'])
            print ', '.join(it.paramlist)
        return 0

    @classmethod
    def _add_interfaces(cls, n, it):
        dnets = 0
        for interface in sorted(n['interfaces']):
            if interface == 'bmc':
                it.addia('mgmt_bmc_net_macs', 'bmc', 'mac')
                it.addia('mgmt_bmc_net_ip', 'bmc', 'ip')
                it.addia('mgmt_bmc_net_name', 'bmc', 'network')
            elif interface == 'bond0':
                it.addia('mgmt_net_macs', 'bond0', 'mac')
                it.addia('mgmt_net_ip', 'bond0', 'ip')
                it.addia('mgmt_net_name', 'bond0', 'network')
                it.addraw('mgmt_net_bonding_mode', '802.3ad')
                it.addraw('mgmt_net_bonding_master', 'bond0')
                try:
                    bondmembers = n['interfaces']['bond0']['bondmembers']
                    if type(bondmembers) == list:
                        bondmembers = ','.join(bondmembers)
                except KeyError:
                    bondmembers = 'eth0, eth1'
                it.addraw('mgmt_net_interfaces', bondmembers)
            elif interface == 'ib0':
                it.addia('ib_0_ip', 'ib0', 'ip')
            elif interface == 'ib1':
                it.addia('ib_1_ip', 'ib1', 'ip')
            else:
                dnets = dnets + 1
                it.addia('data%d_net_name' % dnets, interface, 'network')
                it.addraw('data%d_net_interfaces' % dnets, interface)
                it.addia('data%d_net_ip' % dnets, interface, 'ip')

    @classmethod
    def _read_metadata(cls):
        git_checkout_path='/root/hpcm_data'
        hostname = socket.gethostname()
        filename = '%s/metadata/%s.yaml' % (git_checkout_path, hostname)
        try:
            logging.info("Loading metadata file '%s'", filename)
            with open(filename) as metadatafd:
                metadata = load(metadatafd, Loader=Loader) or {}
                return metadata
        except Exception as e:
            logging.error("Could not read metadata: %s", e)
            return {}

    @classmethod
    def hpcm_repos(cls, nodes, args):
        repodir = '/opt/clmgr/repos/cm-repodata'
        repogroupdir = '/opt/clmgr/repos/cm-repogroups'
        metadata = cls._read_metadata()
        try:
            repos = metadata['repos']
        except KeyError:
            logging.error("repos section not found in metadata")
            return
        for repo in repos:
            path = '%s/%s' % (repodir, repo)
            typefile = '%s/repo-type' % path
            urlfile = '%s/repo-url' % path
            try:
                os.mkdir(path)
            except OSError, e:
                if e.errno == errno.EEXIST:
                    pass
                else:
                    raise
            with open(typefile, 'w') as filefd:
                filefd.write('repo-md')
            with open(urlfile, 'w') as filefd:
                filefd.write(repos[repo])
        try:
            images = metadata['images']
        except KeyError:
            logging.error("images section not found in metadata")
            return
        for image in images:
            if 'repos' not in images[image]:
                logging.error("repos section not found in image %s", image)
                return
            path = '%s/%s' % (repogroupdir, image)
            try:
                os.mkdir(path)
            except OSError, e:
                if e.errno == errno.EEXIST:
                    pass
                else:
                    raise
            for file in os.listdir(path):
                os.unlink('%s/%s' % (path,file))
            for repo in images[image]['repos']:
                src = '%s/%s' % (repodir, repo)
                dst = '%s/%s' % (path, repo)
                os.symlink(src, dst)

    @classmethod
    def run(cls, client):
        ''' Run the action for a single host (this is one instance of a parallel request '''
        action = client.command[1]
        client.output("Not yet implemented", stderr=True)
        return 1

if __name__ == '__main__':
    sys.exit(ConfCommand.run())
