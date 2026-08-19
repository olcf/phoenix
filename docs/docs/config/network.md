# Network Configuration (networks.yaml)
Information about the various cluster networks is stored in the `networks.yaml` file.  These networks can be referenced when configuring node interfaces or generating daemon configuration files. The file consists of a mapping of network names with their attributes. Arbitrary keys can be stored in each network. An example of the structure is shown below:

```yaml
example_network_name:
  network: 192.168.0.0
  netmask: 255.255.255.0
  mtu: 9000
  vlan: 123
another_network:
  network: 10.0.0.0
  netmask: 255.255.255.0
```

## The ipadd Function
Configuration files that support Jinja2 can use the `ipadd` function to ease IP address calculation.

<!-- {% raw %} -->
```yaml
ip: '{{ipadd("example_network_name", nodeindex + 5)}}'
```
<!-- {% endraw %} -->

### Rack-based IP Addresses
Some network topologies create a subnet per rack for routing purposes. In this case, add a `rackmask` to the `networks.yaml` entry. To reserve a `/24` of 256 addresses per rack, the configuration might look like:

```yaml
example_network_name:
  rackmask: 24
```

Then a node might reference this with:

<!-- {% raw %} -->
```yaml
ip: '{{ipadd("example_network_name", nodeindex, rack=racknum)}}'
```
<!-- {% endraw %} -->

## Bonded Interfaces
A node interface can be described as a bond by adding `bondmembers` to it. When the iPXE bootloader generates a boot script for such an interface, it emits a dracut `bond=` kernel argument so that the initramfs brings the bond up before mounting the root filesystem.

```yaml
'@compute':
  interfaces:
    bond0:
      network: example_network_name
      ip: '{{ipadd("example_network_name", nodeindex)}}'
      dhcp: true
      bondmembers: [eth0, eth1]
      bondoptions: mode=802.3ad,miimon=100
```

The interface key (or `interfacename`, if set) becomes the bond name, and the `ip=` argument references the bond rather than any member.

| Attribute | Description |
| --- | --- |
| `bondmembers` | The physical interfaces to add to the bond. Accepts a YAML list or a comma-separated string. Required to mark the interface as a bond. |
| `bondoptions` | Bonding options passed through to dracut. Defaults to `mode=802.3ad,miimon=100`. |

The `mtu` of the referenced network, if set, is applied to the bond through the `bond=` argument instead of `ip=`.

Because a colon separates the fields of `bond=`, neither `bondmembers` nor `bondoptions` may contain one. Multi-valued options such as `arp_ip_target` must therefore be separated with semicolons, which dracut converts back to commas:

```yaml
bondoptions: mode=active-backup,arp_interval=100,arp_ip_target=10.0.0.1;10.0.0.2
```

## AutoInterfaces

{: .notice--danger}
**Warning:** The `autointerfaces` functionality is difficult to understand and will likely be refactored in the future.
