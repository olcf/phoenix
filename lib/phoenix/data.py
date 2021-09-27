#!/usr/bin/env python
"""Data manager"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import phoenix

class Data(object):
    datasource = None

    def __init__(self, name):
        pass

    @classmethod
    def data(cls, *args):
        logging.debug("Called data with key %s", args)
        if cls.datasource is None:
            cls.datasource = phoenix.get_component('datasource')
        logging.debug("calling getkey")
        output = cls.datasource.getval(*args)
        logging.debug("got data value %s", output)
        return output
