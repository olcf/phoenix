# Installation and Upgrades

{: .notice--warning}
**Note:** There is a desire to host a public yum/dnf repository. Is it easy enough to host a release on GitHub?

## Install Phoenix on dnf-based systems (Redhat/Rocky 9+)

```bash
dnf install phoenix
```

## Install Optional Packages

Phoenix is modular, so the base RPM doesn't pull in every package it could possibly use. Consider adding these packages from the OS repositories to extend the functionality of Phoenix.

| Package          | Purpose                                     |
| :--------------- | :-------------------------------------------|
| dnsmasq          | Serve DHCP and tftp                         |
| httpd or nginx   | Serve HTTP                                  |
| ipmitool         | Manage ipmi-based hosts                     |
| ruby             | Support erb templates for file content      |
| python3-net-snmp | Support SNMP out-of-band devices (switches) |
| python3-scapy    | DHCP Option 82 helper                       |

## Upgrade Phoenix
Care is taken to minimize breaking changes between releases. Typically you should be able to just add the new RPM to the repository and run  `dnf update phoenix`. Check the release notes for any special instructions.
