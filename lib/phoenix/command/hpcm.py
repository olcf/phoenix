#!/usr/bin/env python
"""Interaction with HPCM"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import os
import sys
import logging
import argparse
import socket
import errno
import ipaddress

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
from phoenix.network import Network

try:
    usersettings = System.setting('cray_ex')
except:
    usersettings = dict()

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

class HpcmCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="Generate configuration data for HPCM")
        #parser.add_argument('nodes', default=None, type=str, help='Nodes to generate configuration for')
        subparsers = parser.add_subparsers(help='sub-command help', dest='action')
        parser_hpcm = subparsers.add_parser('hpcm', help='hpcm help')
        parser_configure = subparsers.add_parser('configure-cluster', help='Generate a configure-cluster input file')
        parser_discover = subparsers.add_parser('discover', help='Generate a fastdiscover file')
        parser_discover.add_argument('nodes', default=None, type=str, help='Nodes to generate fastdiscover configuration for')
        parser_discover.add_argument('--fakemacs', default=False, action='store_true', help='Use fake MAC addresses where they are missing')
        parser_repos = subparsers.add_parser('repos', help='Manage HPCM repos and repo groups')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        phoenix.parallel.parser_add_arguments_parallel(parser)
        return parser

    @classmethod
    def cli(cls):
        parser = cls.get_parser()
        args = parser.parse_args()

        phoenix.setup_logging(args.verbose)
        if 'nodes' in args:
            nodes = NodeSet(args.nodes)
        else:
            nodes = None

        cmdmap = { 'configure-cluster': cls.configcluster,
                   'discover':          cls.discover,
                   'repos':             cls.repos,
                 }

        if args.action in cmdmap:
            rc = cmdmap[args.action](nodes, args)
        else:
            logging.error("Action %s not yet implemented", args.action)
            return 1
        return rc

    @classmethod
    def configcluster(cls, nodes, args):
        System.load_config()
        output = list()

        networks = Network.networks()

        # Discover section for the admin node
        output.append('[discover]')
        output.append(cls._node_discover('admin1'))
        output.append('')

        # Attributes section
        output.append('[attributes]')
        attr = {
            'admin_house_interface':      '',
            'admin_mgmt_interfaces':      'existing',
            'admin_mgmt_bmc_interfaces':  'existing',
            'discover_skip_switchconfig': 'yes',
            'conserver_logging':          'yes',
            'conserver_ondemand':         'no',
            'conserver_timestamp':        'yes',
            'copy_admin_ssh_config':      'yes',
            'mcell_network':              'no',
            'predictable_net_names':      'yes',
            'redundant_mgmt_network':     'no',
            'mgmt_net_routing_protocol':  'ospf',
            'mgmt_net_subnet_selection':  'next-available',
            'mgmt_vlan_start':            2001,
            'mgmt_vlan_end':              2999,
            'mgmt_ctrl_vlan_start':       3001,
            'mgmt_ctrl_vlan_end':         3999,
            }

        if 'head' in networks and 'vlan' in networks['head']:
            attr['head_vlan'] = networks['head']['vlan']
        #domain_search_path=borg.olcf.ornl.gov,olcf.ornl.gov,ccs.ornl.gov

        # TODO: Pull in other settings from system.yaml

        for key in sorted(attr):
            output.append("%s=%s" % (key, attr[key]))
        output.append('')

        # DNS Section
        output.append('[dns]')
        try:
            output.append("cluster_domain=%s" % System.setting('domain'))
        except:
            pass

        try:
            nscount=0
            for ns in System.setting('nameservers'):
                nscount = nscount + 1
                output.append('nameserver%d=%s' % (nscount, ns))
        except:
            pass
        output.append('')

        # Networks section
        output.append('[networks]')
        for netname in networks:
            netentry = list()
            net = networks[netname]
            netentry.append('name=%s' % netname)
            if netname == 'head' or netname == 'hostmgmt':
                nettype = 'mgmt'
            elif netname == 'head-bmc' or netname == 'hostctrl':
                nettype = 'mgmt-bmc'
            elif netname[0:2] == 'ib':
                nettype = 'ib'
            else:
                nettype = 'data'
            netentry.append('type=%s' % nettype)
            if 'vlan' in net:
                netentry.append('vlan=%d' % net['vlan'])
            netentry.append('subnet=%s' % net['network'])
            netentry.append('netmask=%s' % net['netmask'])
            if 'gateway' in net:
                netentry.append('gateway=%s' % net['gateway'])
            output.append(', '.join(netentry))
        output.append('')

        # Images section
        output.append('[images]')
        output.append('image_types=none')

        print('\n'.join(output))

    @classmethod
    def discover(cls, nodes, args):
        System.load_config()
        Node.load_nodes(nodeset=nodes)
        missingmac = list()
        output = list()
        output.append("[discover]")
        for nodename in nodes:
            result = cls._node_discover(nodename, fakemacs=args.fakemacs, missingmac=missingmac)
            output.append(result)
        if len(missingmac) > 0 and args.fakemacs == False:
            logging.error("Nodes %s are missing a mac address. Specify --fakemacs to continue", NodeSet.fromlist(missingmac))
        else:
            for line in output:
                print(line)
        return 0

    @classmethod
    def _node_discover(cls, nodename, fakemacs=False, missingmac=None):
        n = Node.find_node(nodename)
        it = ParamList(n)
        it.addna('hostname1', 'name')
        if n['plugin'] == 'cray_ex' and n['type'] == 'nc':
            it.addna('internal_name', 'name')
            it.addia('mgmt_bmc_net_name', 'me0', 'network')
            it.addia('mgmt_bmc_net_macs', 'me0', 'mac')
            it.addna('rack_nr', 'racknum')
            it.addna('chassis', 'chassis')
            it.addna('tray', 'slot')
            it.addna('cmm_parent', 'pdu')
            it.addraw('username', 'root')
            it.addraw('password', 'initial0')
            it.addraw('node_controller')
        elif n['plugin'] == 'cray_ex' and n['type'] == 'switch':
            it.addna('internal_name', 'name')
            it.addia('mgmt_bmc_net_name', 'eth0', 'network')
            it.addia('mgmt_bmc_net_macs', 'eth0', 'mac')
            it.addia('mgmt_bmc_net_ip', 'eth0', 'ip')
            it.addraw('username', 'root')
            it.addraw('password', 'initial0')
            if n['switchmodel'] == 'colorado':
                it.addna('rack_nr', 'racknum')
                it.addna('chassis', 'chassis')
                it.addna('tray', 'slot')
                it.addna('cmm_parent', 'pdu')
                it.addraw('switch_controller')
            else:
                it.addraw('external_switch_controller')
        else:
            it.addraw('internal_name', cls._get_internal_name(n))
            cls._add_interfaces(n, it)
            if n['type'] == 'admin' or n['type'] == 'leader':
                it.addna('rootfs', 'rootfs', 'disk')
            elif n['type'] == 'compute':
                it.addna('rootfs', 'rootfs', 'nfs')
                it.addna('nfs_writable_type', 'tmpfs-overlay', 'tmpfs-overlay')
            else:
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
                it.addraw('cmcinventory_managed', 'yes')
                it.addraw('alias_groups', 'cm-geo-name:%s' % n['xname'])
                if 'mac' not in n['interfaces']['bond0']:
                    if missingmac != None:
                        missingmac.append(n['name'])
                    logging.debug("Node %s is missing a mac", n['name'])
                    if fakemacs == True:
                        n['interfaces']['bond0']['mac'] = cls._fakemac(n)
                if 'mac' in n['interfaces']['bond0']:
                    it.addraw('mgmt_net_macs', n['interfaces']['bond0']['mac'])
        return ', '.join(it.paramlist)

    @classmethod
    def _fakemac(cls, n, interface='bond0'):
        ''' Return a fake mac address. Might need a different algorithm'''
        racknum = n['racknum']
        try:
            ipstr = n['interfaces'][interface]['ip'].decode()
        except:
            ipstr = n['interfaces'][interface]['ip']
        ipint = int(ipaddress.ip_address(ipstr)) + (0x22 << 40)
        macstr = "%012x" % ipint
        output = ':'.join([macstr[i:i+2] for i in range(0, len(macstr), 2)])
        return output

    @classmethod
    def _get_internal_name(cls, n):
        if 'hpcm_servicenum' in n:
            servicenum = n['hpcm_servicenum']
        elif 'type' in n:
            nodetype = n['type']
            if nodetype == 'compute':
                servicenum = (2000000000 + n['racknum'] * 10000 +
                              n['chassis'] * 1000 + n['slot'] * 100 +
                              n['board'] * 10 + n['nodenum'])
            elif nodetype == 'admin':
                return 'admin'
            elif nodetype == 'leader':
                servicenum = 200 + n['nodeindex']
            elif nodetype == 'service':
                servicenum = 300 + n['nodeindex']
            elif nodetype == 'login':
                servicenum = 400 + n['nodeindex']
            elif nodetype == 'gateway':
                servicenum = 500 + n['nodeindex']
            elif nodetype == 'utility':
                servicenum = 600 + n['nodeindex']
            else:
                servicenum = 700 + n['nodeindex']
        else:
            servicenum = 800 + n['nodeindex']
        return 'service%d' % servicenum

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
                if 'bondmembers' in n['interfaces']['bond0']:
                    bondmembers = n['interfaces']['bond0']['bondmembers']
                else:
                    bondmembers = cls._get_bond0_bondmembers(n)
                if type(bondmembers) == list:
                    bondmembers = ','.join(bondmembers)
                it.addraw('mgmt_net_interfaces', bondmembers)
            elif interface == 'ib0':
                it.addia('ib_0_ip', 'ib0', 'ip')
            elif interface == 'ib1':
                it.addia('ib_1_ip', 'ib1', 'ip')
            elif '.' in interface:
                logging.debug("Skipping vlan interface %s", interface)
            else:
                dnets = dnets + 1
                it.addia('data%d_net_name' % dnets, interface, 'network')
                it.addraw('data%d_net_interfaces' % dnets, interface)
                it.addia('data%d_net_ip' % dnets, interface, 'ip')

    @classmethod
    def _get_bond0_bondmembers(cls, n):
        if n['plugin'] != 'cray_ex':
            return 'eth0'
        global usersettings
        boardmap = { 'windom':       'enp65s0',
                     'grizzly_peak': 'enp195s0',
                     'bard_peak':    'enp148s0',
                   }
        try:
            if 'bladetype' in n:
                return boardmap[n['bladetype']]
            if 'bladetype' in usersettings:
                return boardmap[usersettings['bladetype']]
        except KeyError:
            pass
        return 'eth0'

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
    def repos(cls, nodes, args):
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
