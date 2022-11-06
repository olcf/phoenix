#!/usr/bin/env python3
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
import socket

from collections import Counter, defaultdict

import phoenix
from phoenix.node import Node
from phoenix.command import Command
from phoenix.system import System

from ClusterShell.Task import Task, task_self
from ClusterShell.NodeSet import NodeSet
from ClusterShell.Worker.EngineClient import EngineClient
from ClusterShell.Worker.Worker import WorkerError, DistantWorker
from ClusterShell.Engine.Engine import E_READ, E_WRITE
from ClusterShell.Event import EventHandler
from ClusterShell.CLI.Display import Display
from ClusterShell.CLI.Error import GENERIC_ERRORS, handle_generic_error
from ClusterShell.CLI.Clush import OutputHandler, DirectOutputHandler, DirectProgressOutputHandler, GatherOutputHandler, RunTimer
from ClusterShell.Topology import TopologyGraph

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
        print("Keyboard interrupt.")
        parallel_exit(128 + signal.SIGINT)
    except GENERIC_ERRORS as exc:
        parallel_exit(handle_generic_error(exc))

    # Error not handled
    task_self().default_excepthook(exception_type, exception_value, traceback)

class PopulationRunTimer(RunTimer):
    def __init__(self, task, total, prog=None, handler=None):
        self.handler = handler
        super(PopulationRunTimer, self).__init__(task, total, prog=prog)

    def update(self):
        statevalues = self.handler.nodemap.values()
        known = len(statevalues)
        if known < self.total:
            pending = '  Pending:{}'.format(self.total - known)
        else:
            pending = ''
        towrite = "  ".join(['{}:{}'.format(k,v) for k,v in Counter(statevalues).items()]) + '{}\r'.format(pending)
        self.erase_line()
        self.wholelen = len(towrite)
        sys.stderr.write(towrite)
        self.started = True

class PopulationOutputHandler(GatherOutputHandler):
    def __init__(self, display, prog=None):
        OutputHandler.__init__(self, prog=prog)
        self._display = display
        self.nodemap = dict()

    def runtimer_init(self, task, ntotal=0):
        """Init timer for live command-completed progressmeter."""
        thandler = PopulationRunTimer(task, ntotal, prog=self._prog, handler=self)
        self._runtimer = task.timer(1.33, thandler, interval=1./3.,
                                    autoclose=True)

    def ev_read(self, worker, node, sname, msg):
        if sname == worker.SNAME_STDOUT:
            self.nodemap[node] = worker.current_msg
        elif sname == worker.SNAME_STDERR:
            self._runtimer_clean()
            self._display.print_line_error(node, msg)
            self._runtimer_set_dirty()

    def ev_close(self, worker, timedout):
        # Worker is closing -- it's time to gather results...
        self._runtimer_finalize(worker)
        # Display command output, try to order buffers by rc
        nodesetify = lambda v: (v[0], NodeSet._fromlist1(v[1]))
        cleaned = False
        for rc, nodelist in sorted(worker.iter_retcodes()):
            ns_remain = NodeSet._fromlist1(nodelist)
            val_map = defaultdict(list)
            for k,v in self.nodemap.items():
                if k not in nodelist:
                    continue
                val_map[v].append(k)
            for buf, nodeset in map(nodesetify, val_map.items()):
                if not cleaned:
                    # clean runtimer line before printing first result
                    self._runtimer_clean()
                    cleaned = True
                self._display.print_gather(nodeset, buf)
                ns_remain.difference_update(nodeset)
            if ns_remain:
                self._display.print_gather_finalize(ns_remain)
        self._display.flush()

        self._close_common(worker)

        # Notify main thread to update its prompt
        self.update_prompt(worker)

class DisplayOptions(object):
    def __init__(self):
        self.diff=False
        self.gatherall=False
        self.gather=False
        self.line_mode=False
        self.label=True
        self.regroup=False

    def __getattr__(self, key):
        return None

def gettopology(nodes, fanout=128):
    # Use servicenodes only for root to avoid ssh issues
    if os.getuid() != 0:
        logging.debug("Topology is currently only enabled for root")
        return None

    # No point in using topology for tiny requests
    if len(nodes) < fanout:
        logging.debug("Skipping topology for small request")
        return None

    servicenodelist = System.setting('servicenodes')
    if servicenodelist is None:
        return None

    servicenodes = NodeSet(servicenodelist)
    destination = nodes.difference(servicenodes)

    if len(destination) == 0:
        logging.debug("Skipping topology because no non-service nodes remain")
        return None

    hostname = socket.gethostname().split('.')[0]
    graph = TopologyGraph()
    graph.add_route(NodeSet(hostname), servicenodes)
    graph.add_route(servicenodes, destination)
    topology = graph.to_tree(hostname)
    logging.debug("Topology is\n%s", topology)
    return topology

def setup(nodes, args):
    sys.excepthook = excepthook

    if type(nodes) is not NodeSet:
        nodes=NodeSet(nodes)
    task = task_self()

    task.set_default('local_worker', PhoenixWorker)
    # Defaults are not sent to gateways, but info is.
    # https://github.com/cea-hpc/clustershell/pull/439
    task.set_info('tree_default:local_workername', 'phoenix.parallel')
    task.set_info('fanout', args.fanout)
    task.set_default("stderr", False)

    if args.local == False:
        task.topology = gettopology(nodes, args.fanout)

    options=DisplayOptions()
    if len(nodes) == 1:
        options.label = False
    color = sys.stdout.isatty()

    display = Display(options, None, color)

    # TODO: Figure out the best way to pick a handler
    if 'wait' in args and args.wait:
        logging.debug("Using wait handler")
        handler=PopulationOutputHandler(display)
    elif len(nodes) > 10:
        handler=GatherOutputHandler(display)
    else:
        handler=DirectProgressOutputHandler(display)
    handler.runtimer_init(task, len(nodes))
    return (task, handler)

def parser_add_arguments_parallel(parser):
    parser.add_argument('-f', '--fanout', type=int, default=System.setting('fanout', 128), help='Fanout value')
    parser.add_argument('-t', '--command-timeout', type=int, default=System.setting('command-timeout', 0))
    parser.add_argument('-T', '--connect-timeout', type=int, default=System.setting('connect-timeout', 20))
    parser.add_argument('-l', '--local', default=False, action='store_true', dest='local')

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
        self.state = None

        if stderr:
            self._stderr = os.pipe()

        self._stdout = os.pipe()
        self.handler = NodeHandler(self, node)

    def _start(self):
        if self._stderr:
            self.streams.set_stream(self.worker.SNAME_STDERR, self._stderr[0], E_READ)
        self.streams.set_stream(self.worker.SNAME_STDOUT, self._stdout[0], E_READ)
        logging.debug("Streams set")

        self.worker._on_start(self.key)

        try:
            self.node = Node.find_node(self.key)
        except KeyError:
            self.output("_start Could not find node %s" % self.key, stderr=True)
            self.mark_command_complete(rc=1)
        else:
            logging.info("Phoenix client submitting command for node %s in thread %d", self.key, getThread() )
            self.worker.executor.submit(Command.run, self)
            logging.info("submitted")
        finally:
            logging.info("returning self")
            return self

    def output(self, message, stderr=False):
        try:
            message = message.encode()
            if not message.endswith(b'\n'):
                message = message + b'\n'
            if stderr and self._stderr:
                os.write(self._stderr[1], message)
            else:
                os.write(self._stdout[1], message)
        except Exception as e:
            logging.debug("Failed to write out message: %s" % e)

    def mark_command_complete(self, rc=None):
        logging.info("Command %s complete for node %s. Closing fd %d", self.command, self.key, self._stdout[1])
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

    def set_state(self, state):
        logging.debug("Node %s setting state to %s", self.key, state)
        self.state = state

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
        #Node.load_nodes(nodeset=self.nodes)
        # FIXME: since implementing nodemaps, we have to load all nodes
        # Find a better way to map determine what nodes to load
        Node.load_nodes()

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
        logging.debug("Inside _set_task")
        # Create the thread executor with the thread count set to the fanout
        try:
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers = self.fanout, thread_name_prefix="phoenix_worker")
        except TypeError:
            # The python 2.x ThreadPoolExecutor doesn't support thread_name_prefix
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers = self.fanout)
        logging.info("set_task done, executor is %s", self.executor)

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
