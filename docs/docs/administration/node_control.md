# Node Control

Phoenix can control the entire lifecycle of nodes.

## Power Control

Use `pxpower` to query and command power of Phoenix devices.

### PDU Support

PDUs are upstream devices that provide power for downstream devices. This may
be a managed PDU, a chassis controller, or other smart device. Add the `--pdu`
flag to target the PDU device instead of the device itself.

## Firmware Control

Phoenix can query and manage firmware versions. Check `pxfirmware` for details.
