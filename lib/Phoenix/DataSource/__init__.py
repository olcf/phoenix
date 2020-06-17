#!/usr/bin/env python
"""Generic Data Source Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging

class DataSource(object):
    def __init__(self, name):
        self.name = name
