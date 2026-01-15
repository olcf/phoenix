# Inventory
The Phoenix inventory keeps track of groups and nodes that Phoenix will manage.

## Groups
A group is a collection of Phoenix nodes. Most Phoenix commands accept a nodelist that can consist of a combination of nodes and groups.

After groups have been defined, the command line tool `pxgroup` can be used to verify group membership:
```bash
# pxgroup login
login[1-2]
```

### Group Definitions via YAML
Group membership is stored in the `groups.yaml` file. It is a simple YAML mapping of group-to-membership entries. The values are processed as a `NodeSet`, meaning that you can comma-separate entries, use node ranges, and include other groups with the `@groupname` syntax. Keep in mind that `@` is a reserved character in YAML, so entries that contain groups will need to be quoted. An example `groups.yaml` file is shown below:

```yaml
switch: eth-spine1,eth-edge1
login: login[1-2]
compute: mycluster[01-32]
user: '@login,@compute'
```

### Group Definitions by Plugins
Node plugins can also define groups based on hardware specifics. Check the documentation for any plugins in use to understand if they manage group membership.

{: .notice--warning}
**Note:** This feature is still a work in progress. No plugins currently manage group membership.

## Nodes
A "node" in Phoenix is any entity that should be tracked or controlled, not just compute nodes. This can include arbitrary equipment such a racks, chassis, switches, PDUs, etc. Phoenix supports a robust hierarchical attribute management system. This makes it easy to express your cluster in a succinct manner with plenty of flexibility.

After nodes have been defined, the command line tool `pxnode` can be used to list the attributes for a node:

```bash
# pxnode login2
login2:
  name: login2
  nodeindex: 2
  plugin: generic
  type: login
```

Or to get a single attribute:

```bash
# pxnode @login type
login1: login
login2: login
```

### Node Definitions via YAML
Node definitions and attributes are stored in the `nodes.yaml` file. The YAML file is processed as an _ordered_ mapping of nodesets to attributes - meaning that later definitions can overwrite previous ones. `nodes.yaml` will process values with `Jinja2`. An example `nodes.yaml` file is shown below:

<!-- {% raw %} -->
```yaml
'@login':
  type: login
  bmc: '{{name}}-bmc'
  image: login_prod
login2:
  image: login_test
```
<!-- {% endraw %} -->

### Node Definitions by Plugins
Node plugins can create nodes to be added to the inventory. This is most useful for tightly integrated systems where racks, chassis, BMCs, and nodes are configured in a pre-defined manner.

{: .notice--warning}
**Note:** This feature is still a work in progress. No plugins currently add nodes to the inventory.

Node plugins can also define attributes for nodes.

### Node Models
A node `model` is a collection of attributes that describe a specific type of hardware. Typical model-specific data might include the node's architecture, manufacturer, and BMC type.

{: .notice--warning}
**Note:** All models are currently built-in to Phoenix or plugins. Phoenix does not support user-defined models, as those attributes could be specified in the `nodes.yaml` file.