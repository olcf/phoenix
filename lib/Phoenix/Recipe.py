#!/usr/bin/env python
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
import Phoenix
#from Phoenix.System import System

class Recipe(object):
    def __init__(self, name=None):
        self.name = name
        self.imagetype = None
        self.initfrom = None
        self.distro = None
        self.packagemanager = None
        self.repos = dict()
        self.steps = list()
        if name is not None:
            self.load_recipe(name)

    def __str__(self):
        result = list()
        result.append("Name:      %s" % self.name)
        result.append("ImageType: %s" % self.imagetype)
        result.append("Distro:    %s" % self.distro)
        result.append("Repos:")
        for key in self.repos:
            result.append("  %s" % key)
        result.append("Steps:")
        for key in self.steps:
            result.append("  %s: %s" % (key.name, key))
        return '\n'.join(result)

    @classmethod
    def list_recipes(cls):
        """ List all known recipes on the system """
        user_provided = os.listdir("%s/recipes" % Phoenix.conf_path)
        return [x[0:-5] for x in sorted(user_provided) if x.endswith(".yaml")]

    @classmethod
    def find_recipe(cls, name):
        """ Given the name of a recipe, find it's path on the
            file system
        """
        # First check in the phoenix_conf area
        filename = "%s/recipes/%s.yaml" % (Phoenix.conf_path, name)
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
            recipedata = load(recipefd, Loader=Loader)

        # Load the data into the recipe structure
        for key, value in recipedata.items():
            if key == "imagetype":
                self.imagetype = value
            elif key == "initfrom":
                self.initfrom = value
            elif key == "distro":
                self.distro = value
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
                        else:
                            self.steps.append(step)
            else:
                logging.warning("Key %s not understood", key)

class Step(object):
    pass

class StepCommand(Step):
    name = 'Command'

    def __init__(self, command):
        self.command = command

    def __str__(self):
        return self.command

class StepPackage(Step):
    name = 'Package'

    def __init__(self, package):
        if type(package) is list:
            self.packages = package
        else:
            self.packages = [package]

    def __str__(self):
        return ','.join(self.packages)
