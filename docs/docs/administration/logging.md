# Node Logging
Collecting and analyzing logs from managed nodes is essential for operating clusters.

## Node System Logs
Phoenix does not explicitly manage or collect system logs (syslog or journal). Consider
configuring `rsyslog` to collect logs over the network, and optionally configure
[VictoriaLogs](https://docs.victoriametrics.com/victorialogs/) for rich querying.

## Console Logs
Node consoles are often made available via the BMC via SSH or `ipmitool sol`.

### conserver

{: .notice--info}
**Note:** Generating a conserver config file is not yet implemented

### pxconsoled

{: .notice--info}
**Note:** `pxconsoled` is not yet implemented
