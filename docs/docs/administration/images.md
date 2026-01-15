# Building Images
Images are built from recipes and saved as artifacts.

## Recipe Definitions

The following parameters can be used to define a recipe:

| Parameter      | Description                                             |
| :--------------| :-------------------------------------------------------|
| architecture   | The target architecture for the image. Defaults to the same architecture where the command is running, but it's useful for cross-building. |
| distro         | Mostly informational. If the `packagemanager` option is unset, the `distro` will be parsed to attempt to guess the correct package manager. |
| packagemanager | Specifies what command should be called to install packages to the image. Supported options are currently `zypper`, `yum`, and `dnf`. If unset, this is assumed from the `distro` setting. |
| initfrom       | The base image that `buildah` should use to build the recipe. The special value `scratch` means that an empty image will be used (and `initpackages` should be specified). Otherwise specify an image that `buildah` can access, such as `ubi` or a custom image that has been pushed to a configured registry. |
| initpackages   | A list of packages to install **outside** of the chroot, useful when creating an image from `scratch`. |
| repos          | A map of `repo_name: url` repo entries to enable in the image. |
| steps          | An ordered list of actions to take to build the image. See below for supportes steps types |
| artifacts      | An ordered list of artifacts to capture from the image. See below for supported artifact types |

### Step Types

| Step      | Description                                             |
| :---------| :-------------------------------------------------------|
| recipe    | Merge the specified recipe into this one                |
| package   | A string or list of strings of package names to install |
| file      | Copy a file from the management node into the image. A string specifies a common source and destination. A mapping with `src` and `dst` can specify different paths |
| command   | Run a command inside the image                          |


### Artifact Types

| Artifact  | Description                                        |
| :---------| :--------------------------------------------------|
| file      | A path or list of paths to copy                    |
| initramfs | Creates a gzip'ed cpio of the image root (boolean) |
| squashfs  | Creates a squashfs of the image root. Optionally specify `output` to control the generated filename or `include` to limit what paths are included |

### Example Recipe

<!-- {% raw %} -->
```yaml
architecture: x86_64
distro: rhel9
packagemanager: dnf
initfrom: scratch
initpackages:
- dnf
- bash
repos:
- https://download.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os/
steps:
  - recipe: rocky-base
  - package:
      - screen
      - golang
  - file: /etc/passwd
  - file:
      src: /root/hosts.mycluster
      dst: /etc/hosts
  - command: systemd-firstboot --timezone=America/New_York --locale=en_US.UTF-8 --locale-messages=en_US.UTF-8

artifacts:
  - squashfs:
      output: {{version}}.squashfs
      include:
        - /opt/rocm-{{version}}
        - /etc/OpenCL/vendors
```
<!-- {% endraw %} -->

## Listing recipes
The `pxrecipe list` command shows all detected recipes.

```yaml
# pxrecipe list
compute
login
rocky-9-base
rocky-9-bootable
```

## Showing a Recipe
The `pxrecipe show recipe_name` command will show the parsed contents of a recipe. If the recipe (or any of its sub-recipe steps) makes use of variables, they must be specified on the command line with `--define variable_name variable_value`.

## Building a Recipe
The `pxrecipe build [options] recipe_name` command builds a recipe from its steps and generates the requested artifacts. If the recipe (or any of its sub-recipe steps) makes use of variables, they must be specified on the command line with `--define variable_name variable_value`. An optional `tag` can be specified with `--tag`, otherwise the current date and time is used for the tag. By default, the `buildah` image is removed after the artifacts are successfully generated, but it can be retained with the `--keep` flag for additional debugging. Failed builds and builds retained with `--keep` need to be cleaned up from Buildah manually.
