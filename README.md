# Phoenix Cluster Provisioning and Management Tool
Phoenix is a library and set of tools to simplify cluster provisioning and management.  It is intended to be lightweight yet powerful.  Its design borrows the best ideas and corrects the worst sins from other cluster management systems used in the past.

Phoenix is currently pre-alpha.  It should be considered a prototype that may significantly change over time.

## Building Phoenix as an RPM
From the git checkout, run:
	python setup.py bdist_rpm

## Running Phoenix from a git checkout
For development, it is easier to use a local checkout than building an RPM.  If you checkout the repo at `$HOME/phoenix`, setup the following environment:

	export PATH=$PATH:$HOME/phoenix/bin
	export PYTHONPATH=$HOME/phoenix/lib
	export PHOENIX_CONF=$HOME/phoenix/conf

If you've never installed the RPM, manually install some dependencies:
	sudo yum -y install clustershell

## Configuring Phoenix and Clustershell
Several yaml-based configuration files are required.  These live in `$PHOENIX_CONF` (`/etc/phoenix/conf` by default)

### system.yaml
This file contains system-level configs.

	system: mycluster
	domain: 'my.org'
	networks:
	  mgmt:
	    network: 10.10.0.0
	    netmask: 255.255.0.0
	    mtu:     9000
	  ipoib:
	    network: 10.11.0.0
	    netmask: 255.255.0.0

### groups.yaml
This file maps nodes into groups. This uses `clustershell` to handle expansion, so values can be a comma-separated list of node ranges (using brackets) and groups.

	rack1: mycluster[1-64]
	rack2: mycluster[65-128]
	compute: '@rack[1-2]'
	login: mycluster-login[1-2]
	batch: mycluster-batch[1-2]
	service: '@login,@batch'
	ethswitch: mycluster-ethsw-rack[1-2]s[1-2]
	ibswitch: mycluster-ibsw-rack[1-2]s[1-4]

### nodes.yaml
This file provides per-node details.  Values can use `jinja2` to interpolate or call functions.  Later values can overwrite previously defined ones (see the `image` key below).

	'@compute':
	  type: compute
	  bmc: '{{name}}-bmc'
	  bmctype: openbmc
	  interfaces:
	    enP5p1s0f0:
	      network: mgmt
	      ip: '{{ ipadd("mgmt", nodeindex + 10) }}'
	      hostname: '{{name}}'
	    ib0:
	      network: ipoib
	      ip: '{{ ipadd("ipoib", nodeindex + 10) }}'
	      hostname: '{{name+"ib"}}'
	  image: compute_20191230
	mycluster128:
	  image: compute_testing

### ClusterShell configuration
Configure the `phoenix` group provider in `/etc/clustershell/groups.conf.d/phoenix.conf`:

	[phoenix]
	map: phoenix_group $GROUP
	list: phoenix_group --list --bare

Set the default group source plugin to be `phoenix` in `/etc/clustershell/groups.conf`:

	[Main]
	default: phoenix

## Command Line Tools
### phoenix_node
This is used to inspect the configuration of a node.

	$ phoenix_node mycluster[1,128]
	mycluster1:
	  bmc: mycluster1-bmc
	  bmctype: openbmc
	  image: compute_20191230
	  interfaces:
	    enP5p1s0f0:
	      hostname: mycluster1
	      ip: 10.10.0.11
	      network: mgmt
	    ib0:
	      hostname: mycluster1ib
	      ip: 10.11.0.11
	      network: ipoib
	  name: mycluster1
	  nodeindex: 1
	  type: compute

	mycluster128:
	  bmc: mycluster128-bmc
	  bmctype: openbmc
	  image: compute_20191230
	  interfaces:
	    enP5p1s0f0:
	      hostname: mycluster128
	      ip: 10.10.0.138
	      network: mgmt
	    ib0:
	      hostname: mycluster128ib
	      ip: 10.11.0.138
	      network: ipoib
	  name: mycluster128
	  nodeindex: 128
	  type: compute

### clush
This is a `ClusterShell` utility

	# clush -w mycluster[1-5] hostname
	mycluster4: mycluster4.my.org
	mycluster1: mycluster1.my.org
	mycluster2: mycluster2.my.org
	mycluster5: mycluster5.my.org
	mycluster3: mycluster3.my.org

It supports "collecting" the results:

	# clush -w mycluster[1-5] -b uname
	---------------
	mycluster[1-5] (5)
	---------------
	Linux

