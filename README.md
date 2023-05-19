# Dareplane Python Utils
This module includes utilities for python which are used within the dareplane 
framework. It contains functionality which shared can be reused within multiple modules.
This currently includes:
1. A `DefaultServer` - which will be loaded an extended within each module to implement the dareplane API
1. `logging` - which contains the standard formatting and a SocketHandler which is modified to send `json` representations of the logging records to the default logging server port (9020). This is used to enable cross process logging.
1. A `StreamWatcher` implementation - which is a utility class to query a single LSL stream into a ring buffer.


## Default Dareplane Server

This default server is used by all `Dareplane` python modules as a starting
point for their `TCP` socket. The idea is to have a single source for common
functionality and patch everything that is model specific on top of this


### Functional incarnations

Currently we are faced with two functional incarnations of servers

1. Spawning functionality from the server in a separate thread, being linked via events to the
   main thread (usually the server).
2. Spawning a subprocess for running functionality - Currently necessary for running `psychopy` as it cannot be run from outside the main thread.
