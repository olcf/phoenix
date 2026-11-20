# Node Control

Phoenix can control the entire lifecycle of nodes.

## Power Control

Use `pxpower` to query and command power of Phoenix devices.

```
pxpower <nodes> [stat|actions|ACTION [PARAM ...]] [options]
```

| Command | Description |
|---|---|
| `stat` (default) | Show the power state. `state`, `status` and `query` are aliases |
| `actions` | List the actions the target accepts |
| `ACTION` | Send an action, such as `On`, `ForceOff` or `GracefulRestart` |

Actions are whatever the device accepts. Phoenix does not translate them, so a
device that accepts `PowerCycle` is sent `PowerCycle`. Action names and
parameter values are matched case-insensitively.

```
pxpower node[01-04] actions
pxpower node[01-04] forceoff --wait off
pxpower node01 gracefulrestart
```

### Options

| Option | Description |
|---|---|
| `--wait STATE` | After the action succeeds, wait until the power state matches `STATE` (e.g. `--wait Off`) |
| `--yaml` | With `actions`, print the accepted actions as node attributes for `nodes.yaml` |
| `--force` | Send the action without checking it against the accepted actions |
| `--manager` | Act on the node's manager (the BMC itself) instead of the system |
| `--chassis` | Act on the node's chassis instead of the system |
| `--target PATH` | Act on an explicit resource path, e.g. `--target Chassis/Board0` |
| `--pdu` | Talk to the node's PDU instead of its BMC (see below) |

Only one of `--manager`, `--chassis` and `--target` may be given.

### Discovered actions

For Redfish devices, the accepted actions are read from the target each time
`pxpower` runs, unless they are set as node attributes. Discovered values are
kept only for the rest of that run. Use `actions --yaml` to save them in
`nodes.yaml` and skip discovery. Each allowable `ResetType` of the
standard reset action is listed by name. Other actions, standard or OEM, are
listed by their full name with the values their parameters accept:

```
$ pxpower node01 actions --manager
ForceRestart, GracefulRestart, Manager.ResetToDefaults(ResetType=ResetAll), Contoso.Process(Name=memtest|burn)
```

Pass parameters as `KEY=VALUE`, or as a bare value when the action has a single
parameter:

```
pxpower node01 manager.resettodefaults resetall --manager
pxpower node01 Contoso.Process Name=memtest --manager
```

With `--force` the action is sent as typed. Actions the target doesn't list
are sent to their [default location](#default-action-locations).

### Node attributes

These attributes are optional. Any that are not set are discovered when needed.

| Attribute | Description |
|---|---|
| `redfishpath` | Path to the system, e.g. `Systems/Node0` |
| `redfish_manager_path` | Path to the manager. Defaults to the system's `ManagedBy` link, then the first manager |
| `redfish_chassis_path` | Path to the chassis. Defaults to the system's `Chassis` link, then the first chassis |
| `redfish_actions` | Actions the system accepts |
| `redfish_manager_actions` | Actions the manager accepts |
| `redfish_chassis_actions` | Actions the chassis accepts |

Actions given with `--target` are always discovered.

Set the actions attributes to limit what `pxpower` will send, or to skip
discovery. They take a list of names, or a mapping of name to a target path or
to a mapping with `target` and `parameters`:

```yaml
node[01-04]:
  redfish_actions: [On, Off, ForceOff]
  redfish_manager_actions:
    ForceRestart:
    Contoso.Process:
      parameters:
        Name: [memtest, burn]
    Contoso.Ping: Managers/BMC/Actions/Oem/Contoso/Ping
```

Set `target` only when the device uses a location other than the default, as
`Contoso.Ping` does above.

#### Default action locations

An action without a `target` is sent to a location built from its name and the
resource path:

| Action name | Example | Sent to |
|---|---|---|
| No dot | `ForceOff` on `Systems/Node0` | `Systems/Node0/Actions/ComputerSystem.Reset` with `{"ResetType": "ForceOff"}` |
| Dotted, starting with the resource's standard type | `Manager.ResetToDefaults` on `Managers/BMC` | `Managers/BMC/Actions/Manager.ResetToDefaults` |
| Any other dotted name | `Contoso.Process` on `Managers/BMC` | `Managers/BMC/Actions/Oem/Contoso.Process` |

The standard type comes from the path: `Systems/...` is `ComputerSystem`,
`Managers/...` is `Manager` and `Chassis/...` is `Chassis`.

To start from what a device accepts, add `--yaml` to `actions`. It prints the
path and actions attributes for the target, ready to paste into `nodes.yaml`
and trim:

```
$ pxpower node01 actions --yaml --manager
redfish_manager_path: Managers/BMC
redfish_manager_actions:
  Contoso.Process:
    parameters:
      Name: [memtest, burn]
  ForceRestart:
  GracefulRestart:
```

Targets are only included where they differ from the defaults. `--yaml` cannot
be used with `--target`, since explicit targets have no attributes.

### PDU Support

PDUs are upstream devices that provide power for downstream devices. This may
be a managed PDU, a chassis controller, or other smart device. Add the `--pdu`
flag to talk to the PDU device instead of the node's BMC. The PDU is set by the
`pdu` and `pdutype` attributes, and its resource path by `pduredfishpath`.

The other options apply to the PDU in the same way, and the attributes above
are read with a `pdu_` prefix (e.g. `pdu_redfish_actions`).

For example, on a Cray EX compute node the node controller (`x1000c0s0b0`) is
the BMC, and the chassis controller (`x1000c0`) is the PDU, which exposes each
blade slot as a `Chassis/BladeN` resource:

```yaml
x1000c0s0b0n0:
  bmctype: redfish
  bmc: x1000c0s0b0
  redfishpath: Systems/Node0
  pdutype: redfish
  pdu: x1000c0
  pduredfishpath: Chassis/Blade0
  pdu_redfish_actions: [On, Off, ForceOff]
```

The `cray_ex` plugin sets all of these except `pdu_redfish_actions`
automatically.

```
pxpower x1000c0s0b0n0 forceoff                  # Systems/Node0 on x1000c0s0b0
pxpower x1000c0s0b0n0 actions --manager         # the node controller itself
pxpower --pdu x1000c0s0b0n0 forceoff            # Chassis/Blade0 on x1000c0
pxpower --pdu x1000c0s0b0n0 actions --target Chassis/Enclosure
```

Powering off the blade slot affects every node on the blade.

## Firmware Control

Phoenix can query and manage firmware versions. Check `pxfirmware` for details.
