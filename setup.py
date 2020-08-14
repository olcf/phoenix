#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
"""Setup tools for phoenix"""

import sys
import os
import imp
import gzip
import argparse
import subprocess
from distutils.core import Command 
from distutils.core import setup
from distutils.command.sdist import sdist
from distutils.command.bdist_rpm import bdist_rpm

class GenerateMan(Command):
    """Custom command to generate man pages"""
    description = 'Generate man pages'
    user_options = []

    def __init__(self, args):
        Command.__init__(self, args)
        self.author = args.get_author()
        self.scripts = args.scripts

    def initialize_options(self):
        pass
    def finalize_options(self):
        pass

    def run(self):
        for script in self.scripts:
            scriptname = script.split('/')[-1]
            sys.dont_write_bytecode = True
            module = imp.load_source(scriptname, script)
            parser = module.get_parser()
            sys.dont_write_bytecode = False
            print "Running generate man for ", script
            if not os.path.exists('man/man1'):
                os.makedirs('man/man1')
            with gzip.open('man/man1/%s.1.gz' % scriptname, 'w') as mpage:
                mpage.write(".TH %s 1\n" % scriptname.upper())
                mpage.write(".SH NAME\n")
                mpage.write("%s - %s\n" % (scriptname, parser.description))
                mpage.write(".SH SYNOPSIS\n")
                parser.print_usage(mpage)
                mpage.write(".SH DESCRIPTION\n")
                for action_group in parser._action_groups:
                    mpage.write(".SS %s\n" % action_group.title)
                    for action in action_group._group_actions:
                        if action.help == argparse.SUPPRESS:
                            continue
                        mpage.write(".TP\n");
                        if len(action.option_strings) == 0:
                            mpage.write('\\fB%s\\fR ' % action.dest)
                        else:
                            for opt in action.option_strings:
                                mpage.write('\\fB%s\\fR ' % opt)
                        if action.choices:
                            mpage.write("{%s}" % ",".join(action.choices))
                        elif action.dest and action.nargs is None:
                                mpage.write('%s ' % action.dest.upper())
                        mpage.write("\n%s\n" % action.help)
                mpage.write(".SH AUTHOR\n")
                mpage.write("%s\n" % self.author)

class CustomSdist(sdist):
    """Override sdist to generate man pages"""
    def run(self):
        self.run_command('generate_man')
        sdist.run(self)

class bdist_rpm_custom(bdist_rpm):
    """bdist_rpm that sets custom options: release, requires"""
    def finalize_package_data (self):
        if self.release is None:
            self.release = release+"%{?dist}"
        if self.requires is None:
            self.requires = requires
        bdist_rpm.finalize_package_data(self)

# Add the phoenix lib to the python path
basedir = os.path.dirname(__file__)
if basedir == "":
    basedir = os.getcwd()
sys.path.insert(0,"%s/lib" % basedir)

scripts = [x for x in os.listdir('bin') if os.path.isfile('bin/%s' % x)]
requires = [ 'clustershell' ]

try:
    ver=subprocess.check_output(["git", "describe"]).strip().split('-')
except:
    ver=['0.1']

try:
    release = ver[1]
except IndexError:
    release = '0'

setup(name = 'phoenix',
    version = ver[0].strip('v'),
    description = 'Phoenix provisioning tool',
    long_description = 'A set of utilities to configure, boot, and manage a cluster',
    author = 'ORNL HPC Operations',
    author_email = 'ezellma@ornl.gov',
    url = 'https://gitlab.ccs.ornl.gov/hpc-admins/phoenix',
    package_dir={'': 'lib'},
    packages = [ 'Phoenix', 'Phoenix.BootLoader', 'Phoenix.Command', 'Phoenix.DataSource', 'Phoenix.OOB', 'Phoenix.Plugins' ],
    #packages=find_packages('lib'),
    scripts = ['bin/%s' % x for x in scripts],
    cmdclass = { 'bdist_rpm': bdist_rpm_custom, 'sdist': CustomSdist, 'generate_man': GenerateMan },
    data_files = [ ('/usr/share/man/man1', ['man/man1/%s.1.gz' % x for x in scripts]),
                   ('/etc/phoenix', []),
                   ('/etc/phoenix/recipes', []),
                   ('/var/opt/phoenix/data', []),
                   ('/etc/clustershell/groups.conf.d', ['contrib/clustershell/phoenix.conf']),
                   ('/usr/lib/systemd/system', ['contrib/pxbootfile.service'])
                 ]
    #install_requires= [ 'clustershell' ]
    )
