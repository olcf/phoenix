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

## VLAN Interfaces
A node interface can be described as a VLAN by adding `vlanparent` and/or naming it following the 4 interface names Dracut supports. The iPXE bootloader then emits a dracut `vlan=` kernel argument alongside the `ip=` for the VLAN.

```yaml
'@compute':
  interfaces:
    'bond0.5':
      network: example_network_name
      ip: '{{ipadd("example_network_name", nodeindex)}}'
      dhcp: true
      vlanparent: bond0
```

Dracut is not told the VLAN id directly; it recovers it by parsing the device name. The interface key (or `interfacename`, if set) must therefore be one of the four naming styles dracut supports, or no bootfile is generated for the interface and a warning is logged:

| Style | Example |
| --- | --- |
| `VLAN_PLUS_VID` | `vlan0005` |
| `VLAN_PLUS_VID_NO_PAD` | `vlan5` |
| `DEV_PLUS_VID` | `bond0.0005` |
| `DEV_PLUS_VID_NO_PAD` | `bond0.5` |

The two `DEV_PLUS_VID` styles already name the parent device, so `vlanparent` only needs to be set explicitly for the `VLAN_PLUS_VID` styles; when both are present they must agree.

The parent does not need an `ip` or `dhcp` attribute of its own:

```yaml
'@compute':
  interfaces:
    bond0:
      network: example_network_name
      bondmembers: [eth0, eth1]
    'bond0.5':
      network: example_vlan_network
      ip: '{{ipadd("example_vlan_network", nodeindex)}}'
      dhcp: true
      vlanparent: bond0
```

This produces `bond=bond0:eth0,eth1:... vlan=bond0.5:bond0 ip=...:bond0.5:none bootdev=bond0.5`.

## Configuring Additional Interfaces at Boot
A bootfile is generated for each interface marked `dhcp`, and by default configures only that one interface. To bring up a second interface in the initramfs as well, mark it `neednet`:

```yaml
'@compute':
  interfaces:
    eth0:
      network: example_network_name
      ip: '{{ipadd("example_network_name", nodeindex)}}'
      dhcp: true
    eth1:
      network: another_network
      ip: '{{ipadd("another_network", nodeindex)}}'
      neednet: true
```

Every bootfile for the node then carries an `ip=` for `eth1` in addition to its own interface, and dracut `bootdev=` points at the interface the bootfile was generated for. `neednet` is independent of `dhcp`, which governs whether a DHCP reservation and a bootfile are created rather than how an interface is configured once booted, so a statically addressed interface can be brought up this way. The `bmc` interface is never configured this way.

{: .notice--warning}
**Note:** Dracut waits for every interface named by an `ip=` argument before mounting the root filesystem. Marking an interface `neednet` whose network is not reachable during provisioning will stall the boot until dracut times out. Only use it for interfaces that must be up in the initramfs.

## IPv6 Interfaces

An interface with an `ip6` is configured from the referenced network's IPv6 definition, using the network's `prefix6` in place of a netmask.

```yaml
example_v6_network:
  network6: '2001:db8:1::'
  prefix6: 64
  gateway6: '2001:db8:1::1'
```

```yaml
'@compute':
  interfaces:
    eth0:
      network: example_v6_network
      ip6: '{{ipadd("example_v6_network", nodeindex)}}'
      dhcp: true
```

Via pxconf bootfiles the address and gateway are automatically bracketed, as dracut requires: `ip=[2001:db8:1::11]::[2001:db8:1::1]:64:${hostname}:eth0:none` on the kernel cmdline.

{: .notice--info}
**Note:** `ipadd` returns an IPv4 address for any network that defines both `network` and `network6`. Pass `family=6` to calculate the IPv6 address of a dual-stack network:
<!-- {% raw %} -->
```yaml
ip6: '{{ipadd("example_dual_stack_network", nodeindex, family=6)}}'
```
<!-- {% endraw %} -->

An interface that defines both an `ip` and an `ip6` is dual-stack, and gets one `ip=` argument per family. A dracut `ip=` carries a single address, so this is the only way to describe both. `bootdev=` is emitted alongside them, as dracut requires it whenever there is more than one `ip=`.

{: .notice--warning}
**Note:** Two `ip=` arguments naming the same device are merged by dracut's `network-manager` and `systemd-networkd` modules, but the older `network-legacy` module rejects the second with `Duplication configurations for '<dev>'` and fails the boot. `network-legacy` is only chosen when NetworkManager is absent from the image, and has been removed outright from RHEL 10 and recent Fedora. An image that still uses it can only be given one address family per interface.

## AutoInterfaces

{: .notice--danger}
**Warning:** The `autointerfaces` functionality is difficult to understand and will likely be refactored in the future.
