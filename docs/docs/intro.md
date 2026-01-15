---
permalink: /docs/
---

# Introduction to Phoenix
Phoenix is a library and set of tools to simplify cluster provisioning and
management. It is intended to be lightweight yet powerful. Its design borrows
the best ideas and corrects the worst sins from other cluster management
systems used in the past.

{: .notice--warning}
**Notice:** Phoenix is currently alpha software. It should be considered a prototype that may significantly change over time.

{: .notice--danger}
**Warning:** This documentation is a work in progress.

## Separation of configuration and data
Most of the system management software available today stores all of its settings in a centralized location, often obfuscated behind proprietary CLI tools or frustrating REST APIs. This makes it difficult to properly manage, as configuration and data are co-located in the same areas.

| Configuration | Data |
| :-------------| :--- |
| Choices that the system administrators make (potentially even before hardware is on-site) | Facts about the system that are not directly chosen by the admins |
| Often static, but can change | May change rapidly, over time |
| Should be stored in plaintext config files, version controlled | Should be stored in a database, with audit logs showing changes, and backups |
| Examples: which image a node should boot, what IP addresses a node should have | Examples: mac addresses, serial numbers, current node state |

Configuration and data should be managed differently, with policies and procedures that are optimized for the information being stored.

{: .notice--success}
**Who decides what is configuration and what is data?** You! Every cluster is different. Phoenix avoids imposing design decisions.

## Minimize State
Distributed stateful systems are often fragile and difficult to maintain. Phoenix tries to avoid state where possible, and when required it delegates state to external systems.

## Extensible
The core of Phoenix is built with plugins so that new functionality can be added easily. Users or vendors can also provide plugins that teach Phoenix about new hardware.

## Modular
Phoenix is designed to function as a loosely coupled toolkit to manage clusters. All of the functionality is opt-in.
