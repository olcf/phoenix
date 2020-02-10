#!/usr/bin/python

import signal
import logging
import requests
import phoenix
from phoenix.Node import Node
from ClusterShell.NodeSet import NodeSet, set_std_group_resolver_config


#when we sigint a phoenix command, find all clustershell tasks and abort them
#We might only be able to abort tasks in the local frame, unfortunately
def phoenix_clustershell_cleanup(signal_int, frame):
  logger.debug('sigint caught, starting cleanup!')

  #print inspect.getmembers(frame)
  #this is potentially expensive, but I can't think of a better way atm
  for object_name, local_object in frame.f_locals.items():
    if isinstance(local_object, Task):
      logger.debug("Aborting a clustershell task.")
      local_object.abort()

  sys.exit(-1)


#this needs called by anything that is using clustershell
#otherwise, we risk hanging the shell
def phoenix_int_handler():
  signal.signal(signal.SIGINT, phoenix_clustershell_cleanup)


#generic redfish request function
#this seemed to be a good idea at first, I'm not sure this implementation met my expectations
def _do_redfish_req(node, request_type, path="", data={}, header={}):

  try:
    nodeobj = Node.find_node(node)
  except KeyError:
    logging.error("Could not find node '%s'", node)
    return "%s: %s" % (node, 'UnknownNode')

  # XXX TODO Pull this from Phoenix
  auth = ('root', 'initial0')

  url = "https://%s/redfish/v1/Systems/%s%s" % (nodeobj['bmc'], nodeobj['redfishpath'], path)
  logging.debug("url: {0}".format(url))

  try:
    if request_type == "get":
      response = requests.get(url, verify=False, auth=auth, timeout=10)
    elif request_type == "post":
      response = requests.post(url, verify=False, auth=auth, headers=header, json=data, timeout=10)
    elif request_type == "put":
      response = requests.put(url, verify=False, auth=auth, headers=header, json=data, timeout=10)
    return response
    #TODO: do more robust error checking of response in do_redfish_req
  except:
    return -1


#there is nothing power specific in the following def
def run_clustershell_command(command, cs_ns, arguments=[]):
  #output of other commands will be passed up to you, you must pass it along

  #How do we tell whether we need to call the worker or if we have another layer of hierarchy to go through?
  #I think clustershell will take care of this for us, so we will just blindly assume we are popping out on the other side as a worker

  #"%hosts" is that magic thing that makes clustershell not spawn a thread/process for every node
  #"%hosts" will be replaced inline with the hosts a task needs to operate on
  arguments = " ".join([",".join(cs_ns), ",".join(arguments), " --worker --cs %hosts"])
  #print "arguments: " + arguments

  task = Task()
  task.set_info("connect_timeout", 65) #I'm not sure this works
  task.set_info("command_timeout", 65) #I'm not sure this works
  ##TODO: acquire fanout from settings or args
  #task.set_info("fanout", 128)
  #task.set_default("stdout_msgtree", False) #this just turns off output?

  logging.debug("Command + Arguments: {0} {0}".format(command, arguments))
  shell_line = "%s %s" % (command, arguments)
  task.shell(shell_line, nodes=cs_ns, remote=False, autoclose="enable_autoclose")
  task.run()
  task.join()

  #get output
  for output, cs_ns in task.iter_buffers():
    print '%s: %s' % (cs_ns, output)

  #It's probably safest to abort only after we've acquired all output from above
  task.abort()


#runs threaded commands on a service node
def run_local_threaded_command(function, cs_ns, arglist=[]):
  """
  Function is the function that we will parallelize.
  arglist is a list of arguments for the function.
  cs_ns is a hostlist of all nodes that we will run the function against.
  """

  rc = 0
  Node.load_nodes(nodeset=cs_ns)

  timeout = 60 #this is the futures timeout. We want requests to timeout first, than futures, then clustershell.
  threads = len(cs_ns)
  executor = concurrent.futures.ThreadPoolExecutor(max_workers = threads, thread_name_prefix='clustershell_phoenix_worker')

  futurelist = []
  for node in cs_ns:
    futurelist.append(executor.submit(function, node, arglist))

  try:
    for future in concurrent.futures.as_completed(futurelist, timeout=timeout):
      try:
        data = future.result()
      except Exception as exc:
        print "Error: %s" % exc
      else:
        print data
  except concurrent.futures.TimeoutError:
    print "Timeout on a node.".format(node)
    rc = rc + 1
    #we can't kill these things without waiting for them :(
    ##catching the exception will end the loop anyway, so let's end it all
    #phoenix_terminate_all(os.getpid(), executor)
  return rc
