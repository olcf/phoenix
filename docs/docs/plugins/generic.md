# Generic Node Plugin
The generic plugin is loaded if a different plugin is not specified.


| Item      | Description                                     |
| :---------| :-----------------------------------------------|
| nodeindex | The last integer part of the node name          |
| nodenums  | A list of all the integer parts of the node name (only present if more than one integer exists) |

For a node defined as:

```yaml
rack2node3:                                                                     
  plugin: generic
```

Phoenix would represent it as:

```bash
# pxnode rack2node3
rack2node3:
  name: rack2node3
  nodeindex: 3
  nodenums:
  - 2
  - 3
  plugin: generic
```
