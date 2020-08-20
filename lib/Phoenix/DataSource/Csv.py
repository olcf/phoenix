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
    data = {}
    data_freshness = {}

    @classmethod
    def _get_filename(cls, key):
        return "%s/%s.csv" % (Phoenix.data_path, key)

    @classmethod
    def _read(cls, key, force=False):
        # Avoid thrashing the reads
        # Consider changing this to stat the file instead
        cur_time = time.time()

        if key in cls.data_freshness:
            if (cls.data_freshness[key] + cls.cachetime) > cur_time:
                return

        try:
            newdata = {}
            with open(cls._get_filename(key), 'r') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                for row in reader:
                    newdata[row[0]] = row[1]
            cls.data[key] = newdata
            cls.data_freshness[key] = time.time()
        except:
            # Assume if you can't read the file it's blank
            cls.data[key] = {}
            cls.data_freshness[key] = time.time()
            pass

    @classmethod
    def _write(cls, key):
        with open(cls._get_filename(key), 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            for datakey in sorted(cls.data[key]):
                writer.writerow([datakey, cls.data[key][datakey]])

    @classmethod
    def getval(cls, key):
    #def __getitem__(self, key):
        logging.debug("Inside CsvDataSource getval for key %s", key)
        parts = key.split('/', 1)
        filekey = parts[0]
        csvkey = parts[1]
        cls._read(filekey)
        try:
            output = cls.data[filekey][csvkey]
        except:
            output = None
        return output

    @classmethod
    def setval(cls, key, value):
    #def __setitem__(self, key, value):
        parts = key.split('/', 1)
        filekey = parts[0]
        csvkey = parts[1]
        # This is probably overkill, but fine for now
        cls._read(filekey)
        cls.data[filekey][csvkey] = value
        # Probably need to throttle this
        cls._write(filekey)
