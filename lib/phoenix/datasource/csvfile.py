#!/usr/bin/env python3
"""CSV Data Source Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import time
import csv
import phoenix

from phoenix.datasource import Datasource

class CsvfileDatasource(Datasource):
    cachetime = 300
    data = {}
    data_freshness = {}

    @classmethod
    def _get_filename(cls, key):
        return "%s/%s.csv" % (phoenix.data_path, key)

    @classmethod
    def _read(cls, key, force=False):
        # Avoid thrashing the reads
        # Consider changing this to stat the file instead
        cur_time = time.time()

        if key in cls.data_freshness:
            if (cls.data_freshness[key] + cls.cachetime) > cur_time:
                logging.debug("Data is fresh, skipping re-read")
                return

        try:
            newdata = {}
            with open(cls._get_filename(key), 'r') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                for row in reader:
                    newdata[row[0]] = row[1]
            cls.data[key] = newdata
            cls.data_freshness[key] = time.time()
        except Exception as e:
            logging.warning("Exception reading datafile: %s", e)
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
    def getval(cls, *args):
        logging.debug("Inside CsvDataSource getval for key %s", args)
        cls._read(args[0])
        try:
            output = cls.data[args[0]]['/'.join(args[1:])]
        except:
            output = None
        return output

    @classmethod
    def setval(cls, *args):
        logging.debug("args[0] is %s", args[0])
        # This is probably overkill, but fine for now
        cls._read(args[0])
        cls.data[args[0]]["/".join(args[1:-1])] = args[-1]
        # Probably need to throttle this
        cls._write(args[0])
