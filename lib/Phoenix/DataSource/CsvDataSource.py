#!/usr/bin/env python
"""CSV Data Source Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import time
import csv
import Phoenix

from Phoenix.DataSource import DataSource

class CsvDataSource(DataSource):
    cachetime = 300

    def __init__(self, name):
        self.name = name
        self.filename = self._get_filename()
        self.data = {}
        self.data_freshness = 0

    def _get_filename(self):
        return "%s/%s.csv" % (Phoenix.data_path, self.name)

    def read(self, force=False):
        # Avoid thrashing the reads
        # Consider changing this to stat the file instead
        cur_time = time.time()
        if (self.data_freshness + self.cachetime) > cur_time:
            return

        try:
            newdata = {}
            with open(self.filename, 'r') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                for row in reader:
                    newdata[row[0]] = row[1]
            self.data = newdata
            self.data_freshness = time.time()
        except:
            # Assume if you can't read the file it's blank
            pass

    def write(self):
        with open(self.filename, 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            for key in sorted(self.data):
                writer.writerow([key, self.data[key]])

    #def getval(self, key):
    def __getitem__(self, key):
        self.read()
        return self.data[key]

    #def setval(self, key, value):
    def __setitem__(self, key, value):
        # This is probably overkill, but fine for now
        self.read()
        self.data[key] = value
        # Probably need to throttle this
        self.write()
