#!/usr/bin/env python3
"""Sync files"""
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import sys
import logging
import argparse

from ClusterShell.NodeSet import NodeSet
import phoenix
import phoenix.parallel
import phoenix.filesync
from phoenix.command import Command
from phoenix.filesync import Filesync

class SyncCommand(Command):
    @classmethod
    def get_parser(cls):
        parser = argparse.ArgumentParser(description="Synchronize files to Phoenix nodes")
        parser.add_argument('nodes', default=None, type=str, help='Nodes to synchronize')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        phoenix.parallel.parser_add_arguments_parallel(parser)
        return parser

    @classmethod
    def cli(cls):
        parser = cls.get_parser()
        args = parser.parse_args()

        phoenix.setup_logging(args.verbose)
        phoenix.adjust_limits()

        nodes = NodeSet(args.nodes)
        (task, handler) = phoenix.parallel.setup(nodes, args)

        cmd = ["sync", args]
        logging.debug("Submitting shell command %s", cmd)
        try:
            task.shell(cmd, nodes=nodes, handler=handler, autoclose=False, stdin=False, tree=True, remote=False)
            task.resume()
        except KeyboardInterrupt as kbe:
            print()
            phoenix.parallel.print_remaining(task, nodes, handler)
        except:
            logging.debug('CLI failed')
            raise
        rc = 0
        return rc

    @classmethod
    def run(cls, client):
        args = client.command[1]
        filesyncclass = phoenix.get_component("filesync", phoenix.filesync.find_provider(client.node))
        rc = filesyncclass.queue_node_sync(client.node, client, args)
        return rc

if __name__ == '__main__':
    sys.exit(SyncCommand.run())
