# HPE Cray EX Node Plugin

This plugin supports HPE Cray EX clusters with special handling for items like xnames, node controllers, and SlingShot.

{: .notice--warning}
**Notice:** This plugin was originally written to support managing Phoenix-HPCM integration. In a future Phoenix release this plugin will be simplified and refactored to better support native Phoenix management of HPE Cray EX Systems.

## System Configuration Items
The `cray_ex` plugin configuration is stored in the `system.yaml` file under the `cray_ex` heading. The relevant keys are:

| Key               | Description                                                                               |
| :-----------------| :-----------------------------------------------------------------------------------------|
| leaders           | A nodeset specifying which HPCM leaders to use                                            |
| racktype          | Useful to indicate that the cabinet is a "hill" TDS rack                                  |
| racks             | A nodeset that includes all the possible rack names that could exist in a system          |
| emptyracks        | A nodeset of empty/missing racks where their components should be reserved for future use |
| startnid          | The first node ID in the system, usually 0 or 1                                           |
| niddigits         | How wide to pad the node ID with zeros, based on cluster size                             |
| nodesperrack      | How many node IDs to reserve per rack (hardware-specific, likely 128 or 256)              |
| autohostctrl      | Automatically populate the hostctrl network (True or False)                               |
| hostctrlvlanstart | The first VLAN ID for the first rack in the hostctrl network                              |
| hostmgmtvlanstart | The first VLAN ID for the first rack in the hostmgmt network                              |
| bladetype         | The default blade type in this system                                                     |
| nicspernode       | Sets the number of HSN NICs per node                                                      |
| autoip            | A mapping of the offset to use for each autoip network (hostctrl, hostmgmt, hsn)          |
| nodegroups        | Used to describe a non-uniform system (with missing blades or mixed blade types)          |
