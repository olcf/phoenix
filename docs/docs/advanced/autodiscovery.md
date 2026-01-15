# Autodiscovery

For small, stable clusters it may make sense to manually keep track of the MAC addresses. As clusters grow, this becomes more unwieldy and an automated update procedure is desired. Phoenix supports several different methods for automatic discovery.

## Switch Discovery
Ethernet switches often keep a database of MAC addresses for its internal forwarding table. A mapping of port to MAC address can often be queried by SNMP or over SSH, though neither method is generically supported across all switches.

Setup a switch to enable SNMP. Its definition might look like:

```yaml
mgmt-switch-1:
  type: switch
  switchtype: snmp
  community: public
```

{: .notice--warning}
**Notice:** It is best practice to use a read-only community string with limited access. `public` is generally recommended against.

The `pxinventory` command can validate communicaiton with the switch and proper parsing of the SNMP data:

```bash
# pxinventory mgmt-switch-1 macmap
```

That should show you all the detected MAC addresses on the switch. Then setup a node to reference that switch and its switch port:

<!-- {% raw %} -->
```yaml
node01:
  interfaces:
    eth0:
      discoverytype: switch
      switch: mgmt-switch-1
      switchport: swp2
       mac: '{{data("mac", name)}}'
```
<!-- {% endraw %} -->

## BMC Discovery
Once a node's BMC has been discovered (or manually configured), the BMC can be used to query information about the other NICs in the node. Currently this is only supported for `RedFish` BMCs. This is the recommended discovery method for HPE Cray EX compute nodes - the BMCs use algorithmic MAC addresses that the `cray_ex` plugin autoconfigures.


The `pxdiscover` command will find the MAC address and store it in the data plugin.

```bash
# pxdiscover node01
node01 is 00:0a:ab:bc:cd:de
# grep node01 /var/opt/phoenix/data/mac.csv 
node01,00:0a:ab:bc:cd:de
```

## DHCP Option-82
DHCP relay agents (typically running on the management Ethernet switch) can be configured to add Option 82 to DHCP requests. Option 82 typically includes the switch `Remote ID` as well as the port `Circuit ID` of the end node. Support for this varies between switch vendors and models, and configuration for Option 82 is outside the scope of this documentation. When the DHCP packet arrives at a DHCP server, it can process the packet to determine the node making the request without needing to recognize its MAC address.

{: .notice--danger}
**Warning:** This feature is not yet complete in Phoenix. Phoenix will not autogenerate DHCP configuration for Option-82-enabled hosts, but it can be manually configured.
