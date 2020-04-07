#!/usr/bin/env python
"""
ClusterShell worker for Phoenix integration.

Calls out to Phoenix functions
"""

################################################################################
# Note: The PhoenixClient and PhoenixWorker were inspired by the ClusterShell  #
#       ExecClient and ExecWorker. Messages go through a pipe to utilize the   #
#       existing underlying engines. In the future this may be re-evaluated to #
#       use a "native" python-based engine instead.                            #
################################################################################

import random
import sys
import os
import time
import logging
import concurrent.futures
import threading
import signal

import Phoenix
from Phoenix.Node import Node

from ClusterShell.Task import Task, task_self
from ClusterShell.NodeSet import NodeSet
from ClusterShell.Worker.EngineClient import EngineClient
from ClusterShell.Worker.Worker import WorkerError, DistantWorker
from ClusterShell.Engine.Engine import E_READ, E_WRITE
from ClusterShell.Event import EventHandler
from ClusterShell.CLI.Display import Display
from ClusterShell.CLI.Error import GENERIC_ERRORS, handle_generic_error
from ClusterShell.CLI.Clush import DirectOutputHandler, DirectProgressOutputHandler, GatherOutputHandler

def getThread():
    return threading.current_thread().ident

def parallel_exit(status, task=None):
    if task:
        task.abort()
        task.join()
        sys.exit(status)
    else:
        for stream in [sys.stdout, sys.stderr]:
            try:
                stream.flush()
            except IOError:
                pass
        os._exit(status)

def excepthook(exception_type, exception_value, traceback):
    try:
        raise exception_value
    except KeyboardInterrupt as kbe:
        print "Keyboard interrupt."
        parallel_exit(128 + signal.SIGINT)
    except GENERIC_ERRORS as exc:
        parallel_exit(handle_generic_error(exc))

    # Error not handled
    task_self().default_excepthook(exception_type, exception_value, traceback)

class DisplayOptions(object):
    def __init__(self):
        self.diff=False
        self.gatherall=False
        self.gather=False
        self.line_mode=False
        self.label=True
        self.regroup=False
        self.groupsource=None
        self.groupbase=None

def setup(nodes, args):
    sys.excepthook = excepthook

    if type(nodes) is not NodeSet:
        nodes=NodeSet(nodes)
    task = task_self()

    # Figure out the best way to pull in ExecWorker and SshWorker
    #from ClusterShell.Worker.Exec import ExecWorker
    #task.set_default('distant_worker', ExecWorker)

    task.set_default('local_worker', PhoenixWorker)
    task.set_default('local_workername', 'phoenix')
    #task.set_default('fanout', 4)
    task.set_info('fanout', args.fanout)
    task.set_default("stderr", True)

    options=DisplayOptions()
    color = sys.stdout.isatty()

    display = Display(options, None, color)

    # TODO: Figure out the best way to pick a handler
    if len(nodes) > 10:
        handler=GatherOutputHandler(display)
    else:
        handler=DirectProgressOutputHandler(display)
    handler.runtimer_init(task, len(nodes))
    return (task, handler)

class NodeHandler(EventHandler):
    def __init__(self, client, node):
        self.node = node
        self.client = client
        self.count = 0
        EventHandler.__init__(self)

class PhoenixClient(EngineClient):

    def __init__(self, node, command, worker, stderr, timeout, autoclose=False):
        EngineClient.__init__(self, worker, node, stderr, timeout, autoclose)
        self._stderr = None
        self.command = command
        self.retries = 0
        self.rc = 0
        self.node = None

        if stderr:
            self._stderr = os.pipe()

        self._stdout = os.pipe()
        self.handler = NodeHandler(self, node)

    def _start(self):
        if self._stderr:
            self.streams.set_stream(self.worker.SNAME_STDERR, self._stderr[0], E_READ)
        self.streams.set_stream(self.worker.SNAME_STDOUT, self._stdout[0], E_READ)

        self.worker._on_start(self.key)

        try:
            self.node = Node.find_node(self.key)
        except KeyError:
            self.output("Could not find node %s" % self.key, stderr=True)
            self.mark_command_complete(rc=1)
        else:
            logging.info("Phoenix client starting for node %s in thread %d", self.key, getThread() )
            self.worker.executor.submit(self.node.run_command, self)
        finally:
            return self

    def dosomething(self):
        #self.output("dosomething for %s bmc %s command %s retry %d in thread %d" % (self.key, self.node['bmc'], self.command, self.retries, getThread() ))
        self.retries = self.retries + 1
        #print(node['bmc'])
        #self.output("Command for %s was %s. BMC is %s" % (self.key, self.command, node.bmc))
        time.sleep(1)
        if random.randrange(5) == 0:
            self.output("Done with sleep, It is done")
            self.mark_command_complete(rc=0)
        else:
            #self.output("Done with sleep, Try again...")
            self.worker.task.timer(1.0, self.handler)

    def output(self, message, stderr=False):
        if not message.endswith('\n'):
            message = message + '\n'
        if stderr and self._stderr:
            os.write(self._stderr[1], message)
        else:
            os.write(self._stdout[1], message)

    def mark_command_complete(self, rc=None):
        logging.info("Command %s complete for node %s", self.key, self.command)
        os.close(self._stdout[1])
        if self._stderr:
            os.close(self._stderr[1])
        if rc:
            self.rc = rc

    def _close(self, abort, timeout):
        if abort and self.rc == 0:
             self.rc = 1
             logging.debug("Node %s trying to _close with abort and rc=0", self.key)

        self.streams.clear()
        self.invalidate()

        if timeout:
            self.worker._on_node_timeout(self.key)
        else:
            self.worker._on_node_close(self.key, self.rc)

    def _handle_read(self, sname):
        # Some of the ClusterShell built-in workers cache local variables
        # as an optimization, but phoenix commands aren't expected to be
        # very talkative. Skip that here for simplicity
        for msg in self._readlines(sname):
            self.worker._on_node_msgline(self.key, msg, sname) 

class PhoenixWorker(DistantWorker):
    SHELL_CLASS = PhoenixClient
    COPY_CLASS = None

    def __init__(self, nodes, handler, timeout=None, **kwargs):
        DistantWorker.__init__(self, handler)
        self._clients_timeout_count = 0
        self._clients_closed_count = 0
        self._clients = []

        self.nodes = NodeSet(nodes)
        self.command = kwargs.get('command')
        self.executor = None # Wait until the task is bound so we know requested fanout

        # Load Phoenix with the nodes we care about
        # Consider if we want to only do this if Node.loaded_nodes is False to
        # avoid reading the conf files again
        Node.load_nodes(nodeset=self.nodes)

        autoclose = kwargs.get('autoclose', False)
        stderr = kwargs.get('stderr', False)
        timeout = kwargs.get('timeout')

        cls = self.__class__.SHELL_CLASS
        for node in self.nodes:
            self._clients.append(cls(node, self.command, self, stderr, timeout, autoclose))

    def _set_task(self, task):
        if self.task is not None:
            # Already attached - bug?
            raise WorkerError("Worker has already been attached to a task")
        self.task = task
        self.fanout = task.info("fanout", 0)
        # Create the thread executor with the thread count set to the fanout
        try:
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers = self.fanout, thread_name_prefix="phoenix_worker")
        except TypeError:
            # The python 2.x ThreadPoolExecutor doesn't support thread_name_prefix
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers = self.fanout)

    # Required by other parts of ClusterShell
    def _engine_clients(self):
        return self._clients

    def _on_node_timeout(self, node):
        DistantWorker._on_node_timeout(self, node)
        self._clients_timeout_count += 1
        self._mark_client_closed()

    def _on_node_close(self, node, rc):
        DistantWorker._on_node_close(self, node, rc)
        self._mark_client_closed()

    # This worker doesn't actually keep track of *which* clients are closed, just the count
    def _mark_client_closed(self):
        self._clients_closed_count += 1
        # Check if this was the last client, and if so, inform the event handler
        if self._clients_closed_count == len(self._clients) and self.eh is not None:
            # For simplicity, ignore legacy support here (no ev_timeout event)
            self.eh.ev_close(self, self._clients_timeout_count > 0)

    def abort(self):
        for client in self._clients:
            client.abort()
        self.executor.shutdown(wait=False)

    def set_write_eof(self):
        pass

WORKER_CLASS = PhoenixWorker
