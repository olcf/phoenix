from textwrap import dedent

import pytest

from phoenix.node import Node

# IpxeBootloader resolves its default template at class definition time.
Node.load_functions()

from phoenix.bootloader import BootloaderConfigError
from phoenix.bootloader.ipxe import IpxeBootloader

def netargs(nodeyaml, interface):
    Node.load_nodes(datastr=dedent(nodeyaml), clear=True)
    return IpxeBootloader._netargs(Node.find_node('n1'), bootinterface=interface)

# (id, node config, interface the bootfile is for, expected arguments)
netargcases = [
    (
        'plain interface uses BOOTIF and needs no bootdev',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip: 10.1.0.11, dhcp: true}
        ''',
        'eth0',
        ['BOOTIF=${mac}',
         'ip=10.1.0.11::10.1.0.1:255.255.255.0:${hostname}:eth0:none'],
    ), (
        # Nothing identifies which NIC booted, so dracut is left to DHCP.
        'no boot interface falls back to dhcp',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip: 10.1.0.11, dhcp: true}
        ''',
        None,
        ['BOOTIF=${mac}', 'ip=dhcp'],
    ), (
        'mtu goes in the 8th field of ip= without a bond',
        '''
        n1:
          interfaces:
            eth0: {network: testnet_jumbo, ip: 10.2.0.11, dhcp: true}
        ''',
        'eth0',
        ['BOOTIF=${mac}',
         'ip=10.2.0.11::10.2.0.1:255.255.255.0:${hostname}:eth0:none:9000'],
    ), (
        'interfacename overrides the interface key',
        '''
        n1:
          interfaces:
            eth0:
              interfacename: bootnet
              network: testnet
              ip: 10.1.0.12
              dhcp: true
        ''',
        'eth0',
        ['BOOTIF=${mac}',
         'ip=10.1.0.12::10.1.0.1:255.255.255.0:${hostname}:bootnet:none'],
    ), (
        # BOOTIF would name a bond member rather than the bond.
        'bond drops BOOTIF and gains bootdev',
        '''
        n1:
          interfaces:
            bond0:
              network: testnet
              ip: 10.1.0.13
              dhcp: true
              bondmembers: [eth0, eth1]
        ''',
        'bond0',
        ['bond=bond0:eth0,eth1:mode=802.3ad,miimon=100',
         'ip=10.1.0.13::10.1.0.1:255.255.255.0:${hostname}:bond0:none',
         'bootdev=bond0'],
    ), (
        'bond takes the mtu itself and bondmembers accepts a string',
        '''
        n1:
          interfaces:
            bond0:
              network: testnet_jumbo
              ip: 10.2.0.13
              dhcp: true
              bondmembers: eth0,eth1
              bondoptions: mode=active-backup
        ''',
        'bond0',
        ['bond=bond0:eth0,eth1:mode=active-backup:9000',
         'ip=10.2.0.13::10.2.0.1:255.255.255.0:${hostname}:bond0:none',
         'bootdev=bond0'],
    ), (
        # A physical parent needs no argument of its own to be built.
        'vlan on a plain parent',
        '''
        n1:
          interfaces:
            'eth0.5':
              network: testnet_vlan
              ip: 10.4.0.11
              dhcp: true
              vlanparent: eth0
        ''',
        'eth0.5',
        ['vlan=eth0.5:eth0',
         'ip=10.4.0.11::10.4.0.1:255.255.255.0:${hostname}:eth0.5:none',
         'bootdev=eth0.5'],
    ), (
        'DEV_PLUS_VID names its own parent, so vlanparent is optional',
        '''
        n1:
          interfaces:
            'eth0.0005':
              network: testnet_vlan
              ip: 10.4.0.12
              dhcp: true
        ''',
        'eth0.0005',
        ['vlan=eth0.0005:eth0',
         'ip=10.4.0.12::10.4.0.1:255.255.255.0:${hostname}:eth0.0005:none',
         'bootdev=eth0.0005'],
    ), (
        'VLAN_PLUS_VID needs vlanparent to name the parent',
        '''
        n1:
          interfaces:
            vlan5:
              network: testnet_vlan
              ip: 10.4.0.13
              dhcp: true
              vlanparent: eth0
        ''',
        'vlan5',
        ['vlan=vlan5:eth0',
         'ip=10.4.0.13::10.4.0.1:255.255.255.0:${hostname}:vlan5:none',
         'bootdev=vlan5'],
    ), (
        # The parent carries no address of its own but still must be built.
        'vlan parent that is a bond is built first',
        '''
        n1:
          interfaces:
            bond0:
              network: testnet_jumbo
              bondmembers: [eth0, eth1]
            'bond0.5':
              network: testnet_vlan
              ip: 10.4.0.15
              dhcp: true
              vlanparent: bond0
        ''',
        'bond0.5',
        ['bond=bond0:eth0,eth1:mode=802.3ad,miimon=100:9000',
         'vlan=bond0.5:bond0',
         'ip=10.4.0.15::10.4.0.1:255.255.255.0:${hostname}:bond0.5:none',
         'bootdev=bond0.5'],
    ), (
        'neednet adds an ip= for another interface, never for bmc',
        '''
        n1:
          interfaces:
            bmc: {network: testnet, ip: 10.1.0.99, dhcp: true, neednet: true}
            eth0: {network: testnet, ip: 10.1.0.15, dhcp: true}
            eth1: {network: testnet_nogateway, ip: 10.3.0.15, dhcp: true, neednet: true}
            eth2: {network: testnet, ip: 10.1.0.16, dhcp: true}
        ''',
        'eth0',
        ['ip=10.1.0.15::10.1.0.1:255.255.255.0:${hostname}:eth0:none',
         'ip=10.3.0.15:::255.255.255.0:${hostname}:eth1:none',
         'bootdev=eth0'],
    ), (
        # Same node, different bootfile: bootdev moves, the rest does not.
        'bootdev follows the interface the bootfile is for',
        '''
        n1:
          interfaces:
            bmc: {network: testnet, ip: 10.1.0.99, dhcp: true, neednet: true}
            eth0: {network: testnet, ip: 10.1.0.15, dhcp: true}
            eth1: {network: testnet_nogateway, ip: 10.3.0.15, dhcp: true, neednet: true}
            eth2: {network: testnet, ip: 10.1.0.16, dhcp: true}
        ''',
        'eth2',
        ['ip=10.3.0.15:::255.255.255.0:${hostname}:eth1:none',
         'ip=10.1.0.16::10.1.0.1:255.255.255.0:${hostname}:eth2:none',
         'bootdev=eth2'],
    ), (
        'dhcp alone does not pull an interface onto the cmdline',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip: 10.1.0.17, dhcp: true}
            eth1: {network: testnet, ip: 10.1.0.18, dhcp: true}
        ''',
        'eth0',
        ['BOOTIF=${mac}',
         'ip=10.1.0.17::10.1.0.1:255.255.255.0:${hostname}:eth0:none'],
    ), (
        # dhcp governs reservations and bootfiles, not initramfs configuration.
        'neednet does not require dhcp',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip: 10.1.0.19, dhcp: true}
            eth1: {network: testnet, ip: 10.1.0.20, neednet: true}
        ''',
        'eth0',
        ['ip=10.1.0.19::10.1.0.1:255.255.255.0:${hostname}:eth0:none',
         'ip=10.1.0.20::10.1.0.1:255.255.255.0:${hostname}:eth1:none',
         'bootdev=eth0'],
    ), (
        # Lets the node boot from one interface and route through another.
        'an empty gateway leaves the field blank',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip: 10.1.0.25, gateway: '', dhcp: true}
            eth1: {network: testnet, ip: 10.3.0.25, neednet: true}
        ''',
        'eth0',
        ['ip=10.1.0.25:::255.255.255.0:${hostname}:eth0:none',
         'ip=10.3.0.25::10.1.0.1:255.255.255.0:${hostname}:eth1:none',
         'bootdev=eth0'],
    ), (
        'a false gateway leaves the field blank',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip: 10.1.0.26, gateway: false, dhcp: true}
        ''',
        'eth0',
        ['BOOTIF=${mac}',
         'ip=10.1.0.26:::255.255.255.0:${hostname}:eth0:none'],
    ), (
        'an interface gateway overrides the network',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip: 10.1.0.27, gateway: 10.1.0.254, dhcp: true}
        ''',
        'eth0',
        ['BOOTIF=${mac}',
         'ip=10.1.0.27::10.1.0.254:255.255.255.0:${hostname}:eth0:none'],
    ), (
        # dracut needs ipv6 bracketed, and takes a prefix rather than a netmask.
        'ipv6 address and gateway are bracketed',
        '''
        n1:
          interfaces:
            eth0: {network: testnet6, ip6: '2001:db8:1::11', dhcp: true}
        ''',
        'eth0',
        ['BOOTIF=${mac}',
         'ip=[2001:db8:1::11]::[2001:db8:1::1]:64:${hostname}:eth0:none'],
    ), (
        'dual stack emits one ip= per family',
        '''
        n1:
          interfaces:
            eth0:
              network: testnet_dual
              ip: 10.5.0.11
              ip6: '2001:db8:5::11'
              dhcp: true
        ''',
        'eth0',
        ['ip=10.5.0.11::10.5.0.1:255.255.255.0:${hostname}:eth0:none',
         'ip=[2001:db8:5::11]::[2001:db8:5::1]:64:${hostname}:eth0:none',
         'bootdev=eth0'],
    ), (
        'suppressing the ipv6 gateway leaves the ipv4 one alone',
        '''
        n1:
          interfaces:
            eth0:
              network: testnet_dual
              ip: 10.5.0.13
              ip6: '2001:db8:5::13'
              gateway6: false
              dhcp: true
        ''',
        'eth0',
        ['ip=10.5.0.13::10.5.0.1:255.255.255.0:${hostname}:eth0:none',
         'ip=[2001:db8:5::13]:::64:${hostname}:eth0:none',
         'bootdev=eth0'],
    ),
]

@pytest.mark.parametrize('nodeyaml,interface,expected',
                         [case[1:] for case in netargcases],
                         ids=[case[0] for case in netargcases])
def test_netargs(nodeyaml, interface, expected):
    assert netargs(nodeyaml, interface) == expected

# (id, node config, interface, expected substring of the error)
errorcases = [
    (
        'vlan name is not a style dracut parses',
        '''
        n1:
          interfaces:
            mgmt: {network: testnet_vlan, ip: 10.4.0.16, dhcp: true, vlanparent: eth0}
        ''',
        'mgmt', 'does not encode a vlan id',
    ), (
        'vlan name disagrees with vlanparent',
        '''
        n1:
          interfaces:
            'eth1.5': {network: testnet_vlan, ip: 10.4.0.17, dhcp: true, vlanparent: eth0}
        ''',
        'eth1.5', 'is built on',
    ), (
        'VLAN_PLUS_VID without a vlanparent names no parent',
        '''
        n1:
          interfaces:
            vlan5: {network: testnet_vlan, ip: 10.4.0.18, dhcp: true}
        ''',
        'vlan5', 'must be set',
    ), (
        'an interface cannot be both a bond and a vlan',
        '''
        n1:
          interfaces:
            'bond0.5':
              network: testnet_vlan
              ip: 10.4.0.19
              dhcp: true
              vlanparent: bond0
              bondmembers: [eth0, eth1]
        ''',
        'bond0.5', 'cannot be both a bond and a vlan',
    ), (
        'a bond cannot be its own member',
        '''
        n1:
          interfaces:
            bond0:
              network: testnet
              ip: 10.1.0.21
              dhcp: true
              bondmembers: [eth0, bond0]
        ''',
        'bond0', 'lists the bond itself',
    ), (
        # A colon would be read as a bond= field separator.
        'bondoptions cannot contain a colon',
        '''
        n1:
          interfaces:
            bond0:
              network: testnet
              ip: 10.1.0.22
              dhcp: true
              bondmembers: [eth0, eth1]
              bondoptions: 'mode=802.3ad:miimon=100'
        ''',
        'bond0', "must not contain ':'",
    ), (
        'an interface needs an address',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, dhcp: true}
        ''',
        'eth0', "missing 'ip'",
    ), (
        'ip6 needs an ipv6 network',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip6: '2001:db8:2::11', dhcp: true}
        ''',
        'eth0', 'missing an ipv6 prefix',
    ), (
        'the network must be defined',
        '''
        n1:
          interfaces:
            eth0: {network: doesnotexist, ip: 10.1.0.23, dhcp: true}
        ''',
        'eth0', 'not defined in networks.yaml',
    ), (
        'the boot interface must exist',
        '''
        n1:
          interfaces:
            eth0: {network: testnet, ip: 10.1.0.11, dhcp: true}
        ''',
        'eth9', "has no interface 'eth9'",
    ),
]

@pytest.mark.parametrize('nodeyaml,interface,message',
                         [case[1:] for case in errorcases],
                         ids=[case[0] for case in errorcases])
def test_config_errors(nodeyaml, interface, message):
    """Bad configuration is reported so the node can be skipped rather than
       silently given a broken cmdline
    """
    with pytest.raises(BootloaderConfigError) as excinfo:
        netargs(nodeyaml, interface)
    assert message in str(excinfo.value)

@pytest.mark.parametrize('devicename,expected', [
    ('vlan5', (None, 5)),
    ('vlan0005', (None, 5)),
    ('eth0.5', ('eth0', 5)),
    ('eth0.0005', ('eth0', 5)),
    ('bond0.4094', ('bond0', 4094)),
    # Neither fully padded nor unpadded, so not a style dracut parses
    ('vlan05', (None, None)),
    ('eth0.05', (None, None)),
    # Not a vlan name at all
    ('eth0', (None, None)),
    ('vlan', (None, None)),
    ('eth0.', (None, None)),
    ('vlan5x', (None, None)),
])
def test_parsevlanname(devicename, expected):
    assert IpxeBootloader._parsevlanname(devicename) == expected

@pytest.mark.parametrize('address,expected', [
    ('2001:db8:1::11', '[2001:db8:1::11]'),
    ('[2001:db8:1::11]', '[2001:db8:1::11]'),
    ('10.1.0.11', '10.1.0.11'),
    ('', ''),
])
def test_bracket(address, expected):
    assert IpxeBootloader._bracket(address) == expected
