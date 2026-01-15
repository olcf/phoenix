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

## AutoInterfaces

{: .notice--danger}
**Warning:** The `autointerfaces` functionality is difficult to understand and will likely be refactored in the future.
