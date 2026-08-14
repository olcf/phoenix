#!/usr/bin/env python3
"""Recipes"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Unable to load CLoader and/or CDumper")
    from yaml import Loader, Dumper

import os
import re
import sys
import platform
import subprocess
import signal
import time
import datetime
import glob
import shutil
import tempfile
import phoenix
import jinja2
from jinja2 import Template
from pathlib import Path

class Recipe(object):
    def __init__(self, name=None, variables=None, tag=None):
        self.name = name
        self.architecture = platform.machine()
        self.root = None
        self.image = None
        self.imagetype = None
        self.initfrom = None
        self.distro = None
        self.initpackages = list()
        self.packagemanager = None
        self.repos = dict()
        self.steps = list()
        self.artifacts = list()
        self.variables = dict()
        if variables is not None:
            self.variables = dict(variables)

        # Resolve the tag before rendering so recipes can use {{tag}}.
        # An explicit --define tag wins over --tag.
        if tag is None:
            tag = default_tag()
        self.variables.setdefault('tag', tag)
        self.tag = self.variables['tag']

        if name is not None:
            self.load_recipe(name)

    def __str__(self):
        result = list()
        result.append("Name:         %s" % self.name)
        result.append("Architecture: %s" % self.architecture)
        result.append("ImageType:    %s" % self.imagetype)
        result.append("Distro:       %s" % self.distro)
        result.append("InitPkgs:     %s" % ",".join(self.initpackages))
        result.append("Repos:")
        for key in self.repos:
            result.append("  %s: %s" % (key, self.repos[key]))
        result.append("Steps:")
        for key in self.steps:
            result.append("  %s: %s" % (key.name, key))
        result.append("Artifacts:")
        for key in self.artifacts:
            result.append("  %s: %s" % (key.name, key))

        return '\n'.join(result)

    @classmethod
    def list_recipes(cls):
        """ List all known recipes on the system """
        try:
            user_provided = (Path(phoenix.conf_path) / "recipes").iterdir()
            return sorted([x.stem for x in user_provided if x.suffix == ".yaml"])
        except OSError:
            return []

    @classmethod
    def find_recipe(cls, name):
        """ Given the name of a recipe, find it's path on the
            file system
        """
        # First check in the phoenix_conf area
        filename = (Path(phoenix.conf_path) / "recipes" / name).with_suffix(".yaml")
        if filename.is_file():
            return filename

        # Next, check for Phoenix "built-in" recipes
        # XXX decide where to put these... opt?
        #raise FileNotFoundError
        #raise IOError
        return None
        
    def load_recipe(self, name):
        """ Reads and processes a recipe.  Adds all the steps
            to this recipe.
        """

        filename = Recipe.find_recipe(name)
        if filename is None:
            logging.error("Could not find a recipe named '%s'", name)
            sys.exit(1)

        # Read the yaml file
        logging.info("Loading recipe file '%s'", filename)
        recipestr = filename.read_text()

        # Process any variables
        template = Template(recipestr, undefined=jinja2.StrictUndefined)
        try:
            recipestr = template.render(**self.variables)
        except jinja2.exceptions.UndefinedError as e:
            print("Error: %s - use --define on the command line" % e)
            sys.exit(1)

        # Load the yaml file
        recipedata = load(recipestr, Loader=Loader) or {}

        # Load the data into the recipe structure
        for key, value in recipedata.items():
            if key == "imagetype":
                self.imagetype = value
            elif key == "architecture":
                self.architecture = value
            elif key == "initfrom":
                self.initfrom = value
            elif key == "distro":
                self.distro = value
                if self.packagemanager is None:
                    self.packagemanager = guesspackagemanager(value)
            elif key == "initpackages":
                if type(value) == list:
                    self.initpackages.extend(value)
                else:
                    self.initpackages.append(value)
            elif key == "repos":
                for reponame, repodesc in value.items():
                    self.repos[reponame] = Repo(reponame, repodesc)
            elif key == "steps":
                for step in value:
                    for steptype in step:
                        if steptype == 'recipe':
                            self.load_recipe(step[steptype])
                        elif steptype == 'command':
                            if type(step['command']) is list:
                                for cmd in step['command']:
                                    self.steps.append(StepCommand(cmd))
                            else:
                                self.steps.append(StepCommand(step['command']))
                        elif steptype == 'package':
                            self.steps.append(StepPackage(step['package']))
                        elif steptype == 'file':
                            self.steps.append(StepFile(step['file']))
                        elif steptype == 'osrelease':
                            self.steps.append(StepOsRelease(step['osrelease'], self))
                        else:
                            self.steps.append(step)
            elif key == "artifacts":
                for artifact in value:
                    for artifacttype in artifact:
                        if artifacttype == 'file':
                            if type(artifact['file']) is list:
                                for fname in artifact['file']:
                                    self.artifacts.append(ArtifactFile(fname))
                            else:
                                self.artifacts.append(ArtifactFile(artifact['file']))
                        elif artifacttype == 'initramfs':
                            self.artifacts.append(ArtifactInitramfs())
                        elif artifacttype == 'squashfs':
                            self.artifacts.append(ArtifactSquashfs(artifact['squashfs']))
                        elif artifacttype == 'push':
                            self.artifacts.append(ArtifactPush(artifact['push'], self))
                        else:
                            logging.warning('Unknown artifact type %s', artifacttype)
            else:
                logging.warning("Key %s not understood", key)

    def createroot(self, tag):
        name = "%s-%s" % (self.name, tag)
        # buildah writes progress to stderr and the name/path we want to
        # stdout, so the streams must be kept apart
        try:
            self.container = subprocess.run(["buildah", "from", "--name", name, "--arch", self.architecture, self.initfrom],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            check=True).stdout.decode().rstrip()
            self.root = Path(subprocess.run(["buildah", "mount", self.container],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            check=True).stdout.decode().rstrip())
        except subprocess.CalledProcessError as cpe:
            logging.error("Command failed: %s", cpe.stderr.decode().rstrip())
            raise RuntimeError
        logging.info("Recipe %s with container %s mounted at %s", self.name, self.container, self.root)

    def setuprepos(self):
        # Probably best to have a Builder class that is subclassed...
        # but that's what refactors are for, right?
        if self.packagemanager == "zypper":
            for repo in self.repos.values():
                repo.addzypper(self.root)
        elif self.packagemanager in ['yum', 'dnf']:
            yumdir = Path(self.root) / 'etc' / 'yum.repos.d'
            yumdir.mkdir(parents=True, exist_ok=True)
            for repo in self.repos.values():
                repo.writeyumrepo(yumdir)
        else:
            logging.error("Unsupported package manager")
            raise RuntimeError

    def installinitpackages(self):
        if len(self.initpackages) == 0:
            logging.debug("No init packages to install")
            return

        logging.info("Installing init packages %s", self.initpackages)
        if self.packagemanager == "zypper":
            command = ["zypper",
                       "--root", self.root,
                       "--non-interactive",
                       "install",
                       "--no-confirm",
                       "--no-recommends"
                       ]
            command.extend(self.initpackages)
            rc = runcmd(command)
            if rc:
                logging.error("Failed to install the init packages")
                raise RuntimeError

        elif self.packagemanager == "dnf":
            command = ["dnf",
                       "--installroot=%s" % self.root,
                       "--forcearch=%s" % self.architecture,
                       "--assumeyes",
                       "install",
                       ]
            command.extend(self.initpackages)
            rc = runcmd(command)
            if rc:
                logging.error("Failed to install the init packages")
                raise RuntimeError

            logging.info("Rebuilding RPM database in container %s", self.container)
            command = ["buildah",
                       "run",
                       "--net=host",
                       self.container,
                       "/bin/bash",
                       "-c",
                       "--",
                       "rpmdb --rebuilddb",
                       ]
            rc = runcmd(command)
            if rc:
                logging.error("Return code %d from rpmdb", rc)

        else:
            logging.error("Unsupported package manager")
            raise RuntimeError
            return

    def commit(self):
        """ Commit the working container to a local image.
        """
        if self.image is not None:
            return self.image

        image = "%s:%s" % (self.name, self.tag)
        logging.info("Committing container %s to image %s", self.container, image)
        rc = runcmd(["buildah", "commit", self.container, image])
        if rc:
            logging.error("Could not commit container %s to image %s", self.container, image)
            raise RuntimeError
        self.image = image
        return image

    def taglatest(self):
        latestlink = Path(phoenix.artifact_path) / 'images' / self.name / 'latest'
        if latestlink.is_symlink():
            try:
                latestlink.unlink()
            except FileNotFoundError:
                pass
        latestlink.symlink_to(Path(self.tag))

    def docleanup(self):
        try:
            subprocess.check_output(["buildah", "umount", self.container])
            subprocess.check_output(["buildah", "rm", self.container])
        except subprocess.CalledProcessError as cpe:
            logging.error("Command failed: %s", cpe.output)
            raise RuntimeError

    def build(self, keep=False):
        if self.initfrom == "scratch" and len(self.initpackages) == 0:
            logging.error("You must specify initpackages when building from scratch")
            return
        logging.info("Building recipe %s with tag %s", self.name, self.tag)

        with ConfirmKeyboardInterrupt():
            self.createroot(self.tag)
            self.setuprepos()
            self.installinitpackages()
            for step in self.steps:
                step.run(self)
            for artifact in self.artifacts:
                artifact.run(self)
            self.taglatest()
            if keep:
                print("Keeping build root at %s" % self.root)
            else:
                self.docleanup()
        print("Successfully built %s/%s" % (self.name, self.tag))

class ConfirmKeyboardInterrupt(object):
    def __enter__(self):
        self.interrupttime = 0
        self.saved_handler = signal.signal(signal.SIGINT, self.handler)

    def handler(self, sig, frame):
        curtime = time.time()
        if curtime - self.interrupttime > 2.0:
            print("Press Ctrl-C again within 2 seconds to abort")
            self.interrupttime = curtime
        else:
            logging.error("Aborted by user. Please cleanup manually")
            #self.saved_handler(*(sig, frame))
            sys.exit(1)

    def __exit__(self, type, value, traceback):
        signal.signal(signal.SIGINT, self.saved_handler)

_default_tag = None

def default_tag():
    """ The default build tag, '<datetime>[-<githash>[-dirty]]'.

        Cached so that recipes merged with the recipe step and repeated
        Recipe instantiations share a tag and only shell out to git once.
    """
    global _default_tag
    if _default_tag is None:
        _default_tag = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        gittag = git_tag(Path(phoenix.conf_path) / "recipes")
        if gittag:
            _default_tag = "%s-%s" % (_default_tag, gittag)
    return _default_tag

def git_tag(path):
    """ If path is inside a git repo, return a tag component of the form
        '<shorthash>' or '<shorthash>-dirty'.  Returns None if path is
        not in a git repo or git is unavailable.
    """
    path = Path(path)
    if not path.is_dir():
        path = path.parent

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(path)] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8",
        )

    # Confirm we are inside a work tree before doing anything else
    inside = git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        logging.debug("Recipe path %s is not in a git repo", path)
        return None

    githash = git("show", "-s", "--pretty=format:%h").stdout.strip()
    if not githash:
        return None

    # Refresh the index so stat-only changes don't cause false positives,
    # then use 'git status --porcelain' as a concise dirty check: any
    # output (tracked changes or untracked files) means dirty.
    git("update-index", "-q", "--refresh")
    status = git("status", "--porcelain")
    dirty = bool(status.stdout.strip())

    return "%s-dirty" % githash if dirty else githash

def guesspackagemanager(distro):
    if distro[0:3] == "sle":
        return "zypper"
    elpattern = re.compile('(?:rh)?el([0-9.]+)')
    result = elpattern.search(distro)
    if result:
        if int(result.group(1)) < 8:
            return "yum"
        else:
            return "dnf"
    raise RuntimeError("Unknown package manager - please manually set")

class Repo(object):
    """ A package repository to enable in an image.

        A repo is defined either as a bare url string or as a mapping with a
        url key plus any number of options.

        dnf/yum options are passed through to the
        package manager unvalidated, so anything the underlying tool
        understands (excludepkgs, gpgkey, priority, ...) may be used.

        Zypper options are limited to enabled, gpgcheck, and priority.
    """

    # Defaults applied unless the recipe overrides them
    defaults = {'enabled': 1, 'gpgcheck': 0}

    # Options zypper can express on the addrepo command line
    zypperoptions = ('enabled', 'gpgcheck', 'priority')

    def __init__(self, name, desc):
        self.name = name
        self.opts = dict()
        if type(desc) is dict:
            if 'url' not in desc:
                logging.error("Repo %s does not define a url", name)
                raise RuntimeError
            self.url = desc['url']
            self.opts = {key: value for key, value in desc.items() if key != 'url'}
        else:
            self.url = desc

        if str(self.url)[0:4] != "http":
            logging.error("Only http(s) repos are supported at this time")
            raise RuntimeError

    def __str__(self):
        if len(self.opts) == 0:
            return self.url
        opts = ", ".join(["%s=%s" % (key, self._format(self.opts[key]))
                          for key in sorted(self.opts)])
        return "%s (%s)" % (self.url, opts)

    @staticmethod
    def _format(value):
        """ Render an option value using dnf repo file syntax """
        if type(value) is bool:
            return "1" if value else "0"
        if type(value) is list:
            return " ".join([str(item) for item in value])
        return str(value)

    def writeyumrepo(self, yumdir):
        """ Write a yum/dnf repo file for this repo into yumdir """
        logging.info("Adding repo %s at %s", self.name, self.url)
        settings = dict(self.defaults)
        settings.update(self.opts)
        with (Path(yumdir) / self.name).with_suffix(".repo").open('w') as f:
            f.write("[%s]\n" % self.name)
            f.write("name = %s\n" % self.name)
            f.write("baseurl = %s\n" % self.url)
            for key in sorted(settings):
                f.write("%s = %s\n" % (key, self._format(settings[key])))

    def _enabled(self, key, default):
        """ Render an option as a zypper on/off flag. Values are compared
            after _format, so yaml booleans and 0/1 work; other spellings
            dnf would accept are treated as on.
        """
        if key not in self.opts:
            return default
        return self._format(self.opts[key]) != "0"

    def addzypper(self, root):
        """ Register this repo with zypper against the image at root """
        logging.info("Adding repo %s at %s", self.name, self.url)
        command = ["zypper",
                   "--root", root,
                   "addrepo",
                   "-g" if self._enabled('gpgcheck', False) else "-G",
                   "--name", self.name,
                   ]
        if 'priority' in self.opts:
            command.extend(["--priority", str(self.opts['priority'])])
        command.append("--enable" if self._enabled('enabled', True) else "--disable")
        command.extend([self.url, self.name])

        for key in self.opts:
            if key not in self.zypperoptions:
                logging.warning("Repo %s option %s is not supported by zypper", self.name, key)

        rc = runcmd(command)
        if rc:
            logging.error("Could not add repo %s at %s", self.name, self.url)
            raise RuntimeError

class Step(object):
    pass

class StepCommand(Step):
    name = 'Command'

    def __init__(self, command):
        self.command = command

    def __str__(self):
        return self.command

    def run(self, recipe):
        logging.info("Running command '%s' against %s", self.command, recipe.root)
        command = ["buildah",
                   "run",
                   "--net=host",
                   recipe.container,
                   "/bin/bash",
                   "-c",
                   "--",
                   self.command
                   ]
        rc = runcmd(command)
        if rc:
            logging.error("Return code %d from command %s", rc, self.command)

class StepPackage(Step):
    name = 'Package'

    def __init__(self, package):
        if type(package) is list:
            self.packages = package
        else:
            self.packages = [package]

    def __str__(self):
        return ','.join(self.packages)

    def run(self, recipe):
        logging.info("Installing packages %s in %s", self.packages, recipe.root)
        command = ["buildah",
                   "run",
                   "--net=host",
                   recipe.container]
        if recipe.packagemanager == 'zypper':
            command.extend([
                "zypper",
                "--non-interactive",
                "install",
                "--no-confirm",
                "--no-recommends",
                ])
        elif recipe.packagemanager == 'dnf':
            command.extend([
                "dnf",
                "--assumeyes",
                "install",
                ])
        else:
            raise RuntimeError("Unknown package manager installation requested")

        command.extend(self.packages)
        rc = runcmd(command)
        if rc:
            logging.error("Could not install packages")
            raise RuntimeError

class StepFile(Step):
    name = 'File'

    def __init__(self, filedesc):
        self.content = None
        self.chown = None
        self.chmod = None
        if type(filedesc) is dict:
            self.content = filedesc.get('content')
            self.chown = filedesc.get('chown')
            self.chmod = filedesc.get('chmod')
            self.dst = filedesc['dst']
            if self.content is not None:
                self.src = None
            else:
                self.src = filedesc['src']
        else:
            self.src = filedesc
            self.dst = filedesc

    def __str__(self):
        if self.content is not None:
            return "(content) => %s" % self.dst
        return "%s => %s" % (self.src, self.dst)

    def run(self, recipe):
        command = ["buildah", "copy"]
        if self.chown is not None:
            command.extend(["--chown", str(self.chown)])
        if self.chmod is not None:
            command.extend(["--chmod", str(self.chmod)])
        command.append(recipe.container)

        tmpfile = None
        if self.content is not None:
            logging.info("Writing content to %s", self.dst)
            tmpfd, tmpfile = tempfile.mkstemp()
            with os.fdopen(tmpfd, 'w') as f:
                f.write(self.content)
            command.extend([tmpfile, self.dst])
        else:
            logging.info("Copying file %s to %s", self.src, self.dst)
            command.extend([self.src, self.dst])

        try:
            rc = runcmd(command)
        finally:
            if tmpfile is not None:
                os.unlink(tmpfile)
        if rc:
            if self.content is not None:
                logging.error("Could not write content to %s", self.dst)
            else:
                logging.error("Could not copy file  %s to %s", self.src, self.dst)
            raise RuntimeError

class StepOsRelease(Step):
    name = 'OsRelease'

    def __init__(self, params, recipe):
        # IMAGE_ID and IMAGE_VERSION always come from the recipe name and
        # tag. A mapping may set any number of additional fields.
        self.fields = {'IMAGE_ID': recipe.name, 'IMAGE_VERSION': recipe.tag}
        if type(params) is dict:
            for key, value in params.items():
                if key in ('IMAGE_ID', 'IMAGE_VERSION'):
                    logging.warning("os-release %s is set from the recipe, ignoring override", key)
                    continue
                self.fields[key] = value

    def __str__(self):
        return " ".join("%s=%s" % (k, v) for k, v in self.fields.items())

    def run(self, recipe):
        osrelease = Path(recipe.root) / 'etc' / 'os-release'
        logging.info("Setting %s in %s", self, osrelease)

        lines = []
        if osrelease.is_file():
            lines = osrelease.read_text().splitlines()

        # Drop any pre-existing lines for the fields we are about to set
        lines = [l for l in lines
                 if not any(l.startswith("%s=" % key) for key in self.fields)]

        for key, value in self.fields.items():
            lines.append('%s="%s"' % (key, value))

        try:
            osrelease.parent.mkdir(parents=True, exist_ok=True)
            osrelease.write_text('\n'.join(lines) + '\n')
        except OSError as e:
            logging.error("Could not write %s: %s", osrelease, e)
            raise RuntimeError

class Artifact(object):
    pass

class ArtifactFile(Artifact):
    name = 'File'

    def __init__(self, filedesc):
        if type(filedesc) is dict:
            self.pattern = filedesc['src']
            self.dst = filedesc['dst']
        else:
            self.pattern = filedesc
            self.dst = None

    def __str__(self):
        if self.dst:
            return '%s => %s' % (self.pattern, self.dst)
        else:
            return self.pattern

    def run(self, recipe):
        # TODO: Make sure the resulting glob doesn't escape the container root
        #       Not really a security issue, as users shouldn't run untrusted recipes
        outputdir = Path(phoenix.artifact_path) / 'images' / recipe.name / recipe.tag
        outputdir.mkdir(parents=True, exist_ok=True)
        logging.info("Saving artifact '%s' to %s", self.pattern, outputdir)

        outputpath = outputdir / self.dst if self.dst else outputdir

        # pathlib glob does not support patterns with absolute paths
        paths = glob.glob(str(recipe.root) + '/' + self.pattern)
        copied = 0
        for path in paths:
            logging.debug("Copying %s to %s", path, outputpath)
            created = shutil.copy2(path, outputpath)
            os.chmod(created, 0o644)
            copied = copied + 1
        if copied == 0:
            logging.error("Artifact file '%s' did not match any files", self.pattern)

class ArtifactInitramfs(Artifact):
    name = 'Initramfs'

    def __init__(self):
        pass

    def __str__(self):
        return "True"

    def run(self, recipe):
        outputdir = Path(phoenix.artifact_path) / 'images' / recipe.name / recipe.tag
        outputdir.mkdir(parents=True, exist_ok=True)
        cpiocommand = "find . | cpio --quiet -H newc -o | pigz -9 -n > %s/initramfs.gz" % outputdir
        logging.info("Saving image root as initramfs artifact")
        command = [ "/bin/bash",
                    "-c",
                    cpiocommand
                    ]
        rc = runcmd(command, cwd=recipe.root)
        if rc:
            logging.error("Could not create initramfs")
            raise RuntimeError

class ArtifactSquashfs(Artifact):
    name = 'Squashfs'

    def __init__(self, params):
        self.output = 'rootdir.squashfs'
        self.include = list()
        if type(params) is dict:
            if 'output' in params:
                self.output = params['output']
            if 'include' in params:
                for path in params['include']:
                    if path.startswith('/'):
                        self.include.append('.' + path)
                    else:
                        self.include.append(path)

    def __str__(self):
        return "True"

    def run(self, recipe):
        outputdir = Path(phoenix.artifact_path) / 'images' / recipe.name / recipe.tag
        outputdir.mkdir(parents=True, exist_ok=True)
        if len(self.include) > 0:
            squashcommand = "mksquashfs %s %s/%s -no-strip" % (" ".join(self.include), outputdir, self.output)
        else:
            squashcommand = "mksquashfs %s %s/%s" % (recipe.root, outputdir, self.output)
        logging.info("Saving image root as squashfs artifact")
        command = [ "/bin/bash",
                    "-c",
                    squashcommand
                    ]
        rc = runcmd(command, cwd=recipe.root)
        if rc:
            logging.error("Could not create squashfs")
            raise RuntimeError
        else:
            logging.info("Created %s/%s", outputdir, self.output)

class ArtifactPush(Artifact):
    """ Push the built image to a container registry with buildah push.

        Defined either as a bare registry string or as a mapping:

          registry: the destination registry, required. May include a
                    path, e.g. registry.example.com/myorg
          image:    the repository name, defaults to the recipe name
          tag:      a tag or list of tags, defaults to the build tag
          format:   the manifest type to push, passed to buildah --format

        buildah push takes a single destination, so each tag is pushed
        separately. Layers already present in the repository are not
        resent, so the extra pushes only upload a manifest.

        Assumes buildah is already logged into the registry.
    """
    name = 'Push'

    formats = ('oci', 'docker', 'v2s2', 'v2s1')

    def __init__(self, params, recipe):
        self.image = recipe.name
        self.tags = [recipe.tag]
        self.format = None
        if type(params) is dict:
            if 'registry' not in params:
                logging.error("Push artifact does not define a registry")
                raise RuntimeError
            self.registry = params['registry']
            self.image = params.get('image', self.image)
            self.format = params.get('format')
            if 'tag' in params:
                tag = params['tag']
                self.tags = tag if type(tag) is list else [tag]
        else:
            self.registry = params

        if len(self.tags) == 0:
            logging.error("Push artifact to %s has an empty tag list", self.registry)
            raise RuntimeError

        for value, what in [(self.registry, 'registry'), (self.image, 'image')] + \
                           [(tag, 'tag') for tag in self.tags]:
            if not isinstance(value, str) or value == '':
                logging.error("Push %s must be a non-empty string, got %r", what, value)
                raise RuntimeError

        if self.format is not None and self.format not in self.formats:
            logging.error("Push format %s is not one of %s", self.format,
                          ", ".join(self.formats))
            raise RuntimeError

    def __str__(self):
        return ", ".join(self.destinations())

    def destinations(self):
        registry = self.registry.rstrip('/')
        return ["%s/%s:%s" % (registry, self.image, tag) for tag in self.tags]

    def run(self, recipe):
        source = recipe.commit()

        for destination in self.destinations():
            logging.info("Pushing %s to %s", source, destination)
            command = ["buildah", "push"]
            if self.format is not None:
                command.extend(["--format", self.format])
            command.extend([source, destination])

            rc = runcmd(command)
            if rc:
                logging.error("Could not push %s to %s", source, destination)
                raise RuntimeError
            logging.info("Pushed %s", destination)

def runcmd(command, cwd=None):
    logging.debug("Running command %s", command)
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setpgrp, cwd=cwd, encoding='utf-8')
    while True:
        output = proc.stdout.readline()
        if output == '' or output == b'':
            rc = proc.poll()
            if rc is not None:
                break
        else:
            logging.debug(output.rstrip())
    return rc
