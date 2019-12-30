#!/usr/bin/env python
"""Plugin for Cray shasta machines"""
# vim: tabstop=4 shiftwidth=4 softtabstop=4

import logging
import re

shasta_regex = re.compile(r'x(?P<racknum>\d+)c(?P<chassis>\d+)([rs](?P<slot>\d+)b(?P<board>\d+)(n(?P<nodenum>\d+))?)?')
node_regex = re.compile(r'x(?P<racknum>\d+)c(?P<chassis>\d+)s(?P<slot>\d+)b(?P<board>\d+)n(?P<nodenum>\d+)')
nc_regex = re.compile(r'x(\d+)c(\d+)s(\d+)b(\d+)')
switch_regex = re.compile(r'x(\d+)c(\d+)r(\d+)b(\d+)')
cc_regex = re.compile(r'x(\d+)c(\d+)')

def set_node_attrs(node):
	''' Sets attributes for nodes in the system
		Note that a "node" in this context could be a
		compute node, nC, cC, cec, or switch
	'''
	logging.debug("Running cray_shasta plugin for node %s", node['name'])

	m = shasta_regex.search(node['name'])

	if m is None:
		logging.debug("Name '%s' did not match the regex", node['name'])
		return

	try:
		node['rack'] = 'x%s' % m.group('racknum')
		node['racknum'] = int(m.group('racknum'))
		node['chassis'] = int(m.group('chassis'))
		node['slot'] = int(m.group('slot'))
		node['board'] = int(m.group('board'))
		node['nodenum'] = int(m.group('nodenum'))
	except TypeError:
		# If the name didn't contain the match, it will return None
		# Converting it to an int will return a TypeError which we just ignore
		pass

	if node['type'] == 'compute':
		node['redfishpath'] = 'Node%d' % node['nodenum']
		node['bmctype'] = 'redfish'
		node['bmc'] = "x{racknum}c{chassis}s{slot}b{board}".format(**node.attr)

	elif node['type'] == 'nc':
		node['redfishpath'] = 'Blade%d' % node['slot']
		node['bmctype'] = 'redfish'
		node['bmc'] = "x{racknum}c{chassis}".format(**node.attr)
		node['mac'] = _algomac(node['racknum'], node['chassis'], node['slot'] + 48, node['board'])
		node['ip'] = _algoipv6addr(node['racknum'], node['chassis'], node['slot'] + 48, node['board'])

	elif node['type'] == 'cc':
		node['mac'] = _algomac(node['racknum'], node['chassis'], 0, 0)
		node['ip'] = _algoipv6addr(node['racknum'], node['chassis'], 0, 0)

	elif node['type'] == 'switch':
		node['redfishpath'] = 'Perif%d' % node['slot']
		node['bmctype'] = 'redfish'
		node['bmc'] = "x{racknum}c{chassis}".format(**node.attr)
		node['mac'] = _algomac(node['racknum'], node['chassis'], node['slot'] + 96, 0)
		node['ip'] = _algoipv6addr(node['racknum'], node['chassis'], node['slot'] + 96, 0)

def _algomac(rack, chassis, slot, idx, prefix=2):
	""" Returns the string representation of an algorithmic mac address """
	return "%02x:%02x:%02x:%02x:%02x:%02x" % (prefix, rack >> 8, rack & 0xFF, chassis, slot, idx << 4)

def _algoipv6addr(rack, chassis, slot, idx, prefix='fc00:0:100:60'):
	""" Returns the EUI64 IP as a string """
	return "%s:%02x:%02xff:fe%02x:%02x%02x" % (prefix, rack >> 8, rack & 0xFF, chassis, slot, idx << 4)

if __name__ == '__main__':
	print _ipv6addr(9000, 1, 2, 1)
