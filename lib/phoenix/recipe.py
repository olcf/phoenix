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
import subprocess
import signal
import time
import datetime
import glob
import shutil
import phoenix
import jinja2
from jinja2 import Template

class Recipe(object):
    def __init__(self, name=None, variables=None):
        self.name = name
        self.root = None
        self.tag = None
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
        if name is not None:
            self.load_recipe(name)

    def __str__(self):
        result = list()
        result.append("Name:      %s" % self.name)
        result.append("ImageType: %s" % self.imagetype)
        result.append("Distro:    %s" % self.distro)
        result.append("InitPkgs:  %s" % ",".join(self.initpackages))
        result.append("Repos:")
        for key in self.repos:
            result.append("  %s" % key)
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
            user_provided = os.listdir("%s/recipes" % phoenix.conf_path)
            return [x[0:-5] for x in sorted(user_provided) if x.endswith(".yaml")]
        except OSError:
            return []

    @classmethod
    def find_recipe(cls, name):
        """ Given the name of a recipe, find it's path on the
            file system
        """
        # First check in the phoenix_conf area
        filename = "%s/recipes/%s.yaml" % (phoenix.conf_path, name)
        if os.path.exists(filename):
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
            return

        # Read the yaml file
        logging.info("Loading recipe file '%s'", filename)
        with open(filename) as recipefd:
            recipestr = recipefd.read()

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
                self.repos.update(value)
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
                        else:
                            logging.warning('Unknown artifact type %s', artifacttype)
            else:
                logging.warning("Key %s not understood", key)

    def createroot(self, tag):
        name = "%s-%s" % (self.name, tag)
        # FIXME add more error handling here
        try:
            self.container = subprocess.check_output(["buildah", "from", "--name", name, self.initfrom], stderr=subprocess.STDOUT).decode().rstrip()
            self.root = subprocess.check_output(["buildah", "mount", self.container], stderr=subprocess.STDOUT).decode().rstrip()
        except subprocess.CalledProcessError as cpe:
            logging.error("Command failed: %s", cpe.output)
            raise RuntimeError
        logging.info("Recipe %s with container %s mounted at %s", self.name, self.container, self.root)

    def setuprepos(self):
        # Probably best to have a Builder class that is subclassed...
        # but that's what refactors are for, right?
        for repo in self.repos:
            if type(self.repos[repo]) == dict:
                try:
                    repourl = self.repos[repo]['url']
                except:
                    pass
            else:
                repourl = self.repos[repo]
            if repourl[0:4] != "http":
                logging.error("Only http(s) repos are supported at this time")
                raise RuntimeError
                return
            if self.packagemanager == "zypper":
                logging.info("Adding repo %s at %s", repo, repourl)
                command = ["zypper",
                           "--root", self.root,
                           "addrepo",
                           "-G",
                           "--name", repo,
                           "--enable",
                           repourl,
                           repo
                           ]
                rc = runcmd(command)
                if rc:
                    logging.error("Could not add repo %s at %s", repo, repourl)
                    raise RuntimeError
            elif self.packagemanager in ['yum', 'dnf']:
                with open('%s/etc/yum.repos.d/%s.repo' % (self.root, repo), 'w') as f:
                    f.write("[%s]\n" % repo)
                    f.write("name = %s\n" % repo)
                    f.write("baseurl = %s\n" % repourl)
                    f.write("enabled = 1\n")
                    f.write("gpgcheck = 0\n")
            else:
                logging.error("Unsupported package manager")
                raise RuntimeError
                return

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

        else:
            logging.error("Unsupported package manager")
            raise RuntimeError
            return

    def docleanup(self):
        try:
            subprocess.check_output(["buildah", "umount", self.container])
            subprocess.check_output(["buildah", "rm", self.container])
        except subprocess.CalledProcessError as cpe:
            logging.error("Command failed: %s", cpe.output)
            raise RuntimeError

    def build(self, tag=None, keep=False):
        if self.initfrom == "scratch" and len(self.initpackages) == 0:
            logging.error("You must specify initpackages when building from scratch")
            return
        if tag == None:
            tag = datetime.datetime.now().strftime("%Y%m%d%H%M")
        self.tag = tag
        self.variables['tag'] = tag
        logging.info("Building recipe %s with tag %s", self.name, tag)

        with ConfirmKeyboardInterrupt():
            self.createroot(tag)
            self.setuprepos()
            self.installinitpackages()
            for step in self.steps:
                step.run(self)
            for artifact in self.artifacts:
                artifact.run(self)
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

def guesspackagemanager(distro):
    if distro[0:3] == "sle":
        return "zypper"
    elpattern = re.compile('(?:rh)?el([0-9\.]+)')
    result = elpattern.search(distro)
    if result:
        if int(result.group(1)) < 8:
            return "yum"
        else:
            return "dnf"
    raise RuntimeError("Unknown package manager - please manually set")

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
        if type(filedesc) is dict:
            self.src = filedesc['src']
            self.dst = filedesc['dst']
        else:
            self.src = filedesc
            self.dst = filedesc

    def __str__(self):
        return "%s => %s" % (self.src, self.dst)

    def run(self, recipe):
        logging.info("Copying file %s to %s", self.src, self.dst)
        command = ["buildah",
                   "copy",
                   recipe.container,
                   self.src,
                   self.dst
                   ]
        rc = runcmd(command)
        if rc:
            logging.error("Could not copy file  %s to %s", self.src, self.dst)
            raise RuntimeError

class Artifact(object):
    pass

class ArtifactFile(Artifact):
    name = 'File'

    def __init__(self, filedesc):
        self.pattern = filedesc

    def __str__(self):
        return self.pattern

    def run(self, recipe):
        # TODO: Make sure the resulting glob doesn't escape the container root
        #       Not really a security issue, as users shouldn't run untrusted recipes
        outputdir = os.path.join(phoenix.artifact_path, 'images', recipe.name, recipe.tag, '')
        try:
            os.makedirs(outputdir)
        except FileExistsError:
            pass
        logging.info("Saving artifact '%s' to %s", self.pattern, outputdir)
        paths = glob.glob(recipe.root + '/' + self.pattern)
        for path in paths:
            logging.debug("Copying %s to %s", path, outputdir)
            shutil.copy(path, outputdir)

class ArtifactInitramfs(Artifact):
    name = 'Initramfs'

    def __init__(self):
        pass

    def __str__(self):
        return "True"

    def run(self, recipe):
        outputdir = os.path.join(phoenix.artifact_path, 'images', recipe.name, recipe.tag, '')
        try:
            os.makedirs(outputdir)
        except FileExistsError:
            pass
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
        outputdir = os.path.join(phoenix.artifact_path, 'images', recipe.name, recipe.tag, '')
        try:
            os.makedirs(outputdir)
        except FileExistsError:
            pass
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
            logging.info("Created %s/%s" % (outputdir, self.output))

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
