# Default Dareplane Module Server

This default server is used by all `Dareplane` python modules as a starting
point for their `TCP` socket. The idea is to have a single source for common
functionality and patch everything that is model specific on top of this

# Functional incarnations

Currently we are faced with two functional incarnations of servers

1. Spawning functionality from the server in a separate thread, being linked via events to the
   main thread (usually the server).
2. Spawning a subprocess for running functionality - Currently necessary for running `psychopy` as it cannot be run from outside the main thread.
