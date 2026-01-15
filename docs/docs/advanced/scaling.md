# Scaling (Phoenix Flock)

A single Phoenix server should be able to handle a cluster consisting of several hundred compute nodes (depending on the provisioning method and the hardware specifications of the server). Growing beyond that might require deploying a Phoenix "flock" of servers for horizontal scale-out. Flock servers operate (mostly) independently of each other.

## Requirements

### Network
Phoenix flock nodes require the same network connectivity as a single-server setup. Passwordless SSH connectivity is required between the Phoenix flock servers.

### Install Packages
First, make sure that the Phoenix package and all of its dependencies (ClusterShell, Jinja2, etc) are installed. Next, determine which of the optional packages (apache/nginx, dnsmasq, etc.) should be installed.

### Shared Storage
Phoenix artifacts (such as image content) need to be made available to all the nodes in the Phoenix flock. Phoenix does not mandate or recommend any specific solution, and configuration is outside the scope of this guide. Some options include:

- Use an external Network Attached Storage (NAS) system.
- Configure the primary Phoenix server as a NFS server that the other flock nodes mount. The primary server becomes a single point of failure.
- Replicate artifacts to local storage in each flock node using `rsync` in a cron job or something more robust like [Syncthing](https://syncthing.net/).
- Configure a parallel POSIX file system across the flock nodes such as [Gluster](https://www.gluster.org/) or [Ceph](https://ceph.io). Optionally use an object store such as MinIO or Garage with a fuse-based mountpoint for each flock node. Each of these options can be quite complicated.

### Configuration Synchronization
Make sure that the Phoenix configuration files (typically in `/etc/phoenix`) are synchronized across all the servers in the flock. It is recommended to use a configuration management system like Puppet or Ansible or store configuration in Shared Storage.

### Data Sources
If any data sources are used in the configuration, make sure that they are multi-node friendly (using a database or a shared filesystem).

## Update configs to use multiple servers

Determine which hosts will be used for the flock.

{: .notice--info}
**Should I include the primary Phoenix host in the list?** It depends on your operational model. If you want all of the Phoenix management nodes to be identical, then yes, you should include it. If you have a primary management host that is generally the system administration "jump box" then it probably makes sense to exclude it. Work will be divided evenly between all the listed hosts and collected by the host that issued the command. For large systems, this can be a fair amount of text processing, so excluding it from the hierarchy is probably a good idea.

Update the `system.yaml` file to add the `servicenodes` key. It is a ClusterShell NodeSet:

```yaml
servicenodes: mycluster-mgmt[1-3]
```

This activates Phoenix to use these flock nodes in a hierarchy for commands where the node count is greater than the `fanout`. Most commands support a custom fanout count with the `--fanout` flag, but it can also be set globally in the `system.yaml` file:

```yaml
fanout: 128
```

### Deploy DHCP on multiple servers

{: .notice--danger}
**Warning:** The Phoenix features mentioned below are not implemented yet.

Multiple DHCP servers can be configured on a network, but caution must be taken to make sure they do not conflict. If dynamic IP ranges are in use, each server should be given a unique range. With static-only assignments, there are multiple options:

- All DHCP servers answer for all nodes. The first to answer wins, which may cause uneven loading between the servers.
- A single DHCP server answers for a given node. This ensures even load balancing, but it not resilient in the case of a DHCP server outage.
- A pair of DHCP servers answer for a given node. This is a mixture between the two previous modes. This mode can cause some load imbalance, but it allows DHCP servers to be offline.

### Update iPXE Bootfiles

By default iPXE will use the DHCP server to download the kernel and initrd files. If you deploy DHCP on all the Phoenix flock nodes, this should already be distributed. Otherwise, you can specify the `http_server` attribute on a node.

This simple example manually divides compute nodes between three IP addresses:

```yaml
compute[01-20]:
  http_server: 192.168.0.10
compute[21-40]:
  http_server: 192.168.0.11
compute[41-64]:
  http_server: 192.168.0.12
```

In the more complex example below, the IP address is calculated by taking the modulus of the node index and adding it to the `management` network (defined in `networks.yaml`):

<!-- {% raw %} -->
```yaml
compute[01-64]:
  http_server: '{{ ipadd("management", nodeindex % 3 + 10) }}'
```
<!-- {% endraw %} -->