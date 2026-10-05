#!/usr/bin/env python3
"""rsync FileSync Functions"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import logging
import re
import phoenix
from ClusterShell.Task import task_self
from ClusterShell.Worker.Exec import ExecWorker

from phoenix.filesync import Filesync

import os
import threading

class RsyncFilesync(Filesync):
    filesynctype = "rsync"

    @classmethod
    def _validate_chown(cls, value):
        regex = r'^\w+:\w+$'
        return bool(re.search(regex, value))

    @classmethod
    def _validate_chmod(cls, value):
        regex = r'^(?:[0-7]{3,4}|(?:[ugoa]*[-+=][rwxXstugo]*)(?:,[ugoa]*[-+=][rwxXstugo]*)*)$'
        return bool(re.search(regex, value))

    @classmethod
    def node_sync(cls, nodename, fileobjectlist, task=None, timeout=60, parallel=False):
        """Sync one node using rsync

        Args:
            nodename: a string that can be used to connect to the node
            fileobjectlist: a list of FileObjects to synchronize
            task: optional ClusterShell task to use instead of task_self()
            timeout: timeout to provide to task.shell
            parallel: boolean to issue multiple rsync commands in parallel
                      defaults to false since normally Phoenix will parallelize
                      over nodes

        Returns:
            A tuple of:
            - ok: boolean (True means no errors)
            - msg: status info or 'Ok'
        """
        if task is None:
            task = task_self()

        rc = 0

        # TODO: combine same-dest sources into a single command to reduce ssh connection overhead
        for index, entry in enumerate(fileobjectlist):
            if entry.src is None:
                if entry.content is not None:
                    logging.warning('rsync filesync does not yet support content for %s (node %s)', entry.dst, nodename)
                    continue
                if entry.template is not None:
                    logging.warning('rsync filesync does not yet support template for %s (node %s)', entry.dst, nodename)
                    continue
                logging.error('Blank source')
                continue

            if entry.chown is not None:
                if not cls._validate_chown(entry.chown):
                    logging.error('chown string %s is not supported by rsync', entry.chown)
                    continue
                chownstr = f'--chown={entry.chown}'
            else:
                chownstr = ''

            if entry.chmod is not None:
                if not cls._validate_chmod(entry.chmod):
                    logging.error('chmod string %s is not supported by rsync', entry.chmod)
                    continue
                chmodstr = f'--chmod={entry.chmod}'
            else:
                chmodstr = ''

            # Assume newly booted nodes won't have correct host certs yet
            # Hard-code this method for now, make it configurable later
            sshoptions = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null'
            cmd = f'rsync -a {chownstr} {chmodstr} -e "ssh {sshoptions}" {entry.src} {nodename}:{entry.dst}'
            logging.info('RSyncing %s to %s:%s in pid:tid %d:%d (command %s)', entry.src, nodename, entry.dst, os.getpid(), threading.get_native_id(), cmd)
            task.shell(cmd, key=index, timeout=timeout)

            if not parallel:
                task.resume()
                rc = task.node_retcode(index)
                if rc != 0:
                    return (False, 'rsync error')

        if parallel:
            task.resume()
            if task.max_retcode() != 0:
                return (False, 'rsync error')

        return (True, 'Ok')
