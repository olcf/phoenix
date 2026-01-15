# Configuration Basics
Each configuration file is documented independently, but some attributes are common to all Phoenix configuration files.

## Relaxed Schema
Any Phoenix plugin can read and use any configuration file, so a strict schema is not enforced. You can store arbitrary data in each configuration file. This means that typos in your keys might be hard to spot - if you receive an error about a missing configuration item, carefully check its spelling.

## YAML
All of the Phoenix configuration files are written in [YAML](https://yaml.org) and stored in the configuration directory (defaults to `/etc/phoenix` for a system-level install). Some tips about using YAML:

- Feel free to add comments with the `#` character
- Use spaces instead of tabs
- You may need to quote strings with special characters
  - Group names that start with `@`
  - Strings containing Jinja2 syntax with `{curly braces}`
- Consider using a linter (like [yamllint](https://github.com/adrienverge/yamllint)) to validate your configuration before committing it to your configuration management system

An example yaml file follows:

```yaml
---
# ^ The three dashes at the beginning are an optional 'start of document marker'
# Comments start with the pound/hash sign
key_name: A string as a value
another_key:
  - A
  - list
  - as
  - value
```

## Jinja2
[Jinja2](https://jinja.palletsprojects.com/) is a templating engine that Phoenix uses for certain configuration items and templates. Check the documentation for each configuration file to determine if Jinja2 is enabled. For YAML documents, Jinja2 is typically only enabled for values (the whole file is not run through the templating engine).

The most common use case is to replace a variable. Variables are enclosed by double curly brackets, for example:

<!-- {% raw %} -->
```yaml
bmc: '{{name}}-bmc'
```
<!-- {% endraw %} -->

