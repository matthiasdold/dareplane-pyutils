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

## Logging

The logging tools allow two main entry point, which are `from dareplane_utils.logging.logger import get_logger`, which is used to get a logger with the default configuration and `from dareplane_utils.logging.server import LogRecordSocketReceiver` which is used to spawn up a server for consolidating logs of different processes.

## StreamWatcher

StreamWatcher are a convenient utility around LSL stream inlets. They are basically a ring buffer for reading data to a numpy array.
StreamWatchers are:

1. initialized with a target stream name and a buffer size in seconds specified by `buffer_size`
2. connected to the target LSL stream
3. updated to fetch the latest data (usually done in a loop)

#### initialize a StreamWatcher

```python
from dareplane_utils.stream_watcher.lsl_stream_watcher import StreamWatcher

STREAM_NAME = "my_stream"
BUFFER_SIZE_S = 5   # the required buffer size will be calculated from the LSL
                    # streams meta data

sw = StreamWatcher(
    STREAM_NAME,
    buffer_size_s=BUFFER_SIZE_S,
)
```

#### connect to the stream

```python
# Either use the self.name or a provided identifier dict to hook up to an LSL stream
sw.connect_to_stream()
```

#### update

```python
sw.update()
```

Update will call the following method:

```python

    def update(self):
        """Look for new data and update the buffer"""
        samples, times = self.inlet.pull_chunk()
        self.add_samples(samples, times)
        self.samples = samples
        self.n_new += len(samples)

```

#### Getting data

To get the data from the StreamWatcher you can either grab the full ring buffer
from the instance attributes

```python
sw.buffer    # ring buffer for data
sw.buffer_t  # ring buffer for time stamps
sw.curr_i    # current position of the head in the ring buffer
```

or you usually want the more convenient way by using the `unfold_buffer` method,
which returns a chronologically sorted array ([-1] is the most recent data
point and [0] is the oldest data point).

```python
sw.unfold_buffer()     # sorted data
sw.unfold_buffer_t()   # sorted time stamps


## The above is using the following implementation
    def unfold_buffer(self):
        return np.vstack(
            [self.buffer[self.curr_i :], self.buffer[: self.curr_i]]
        )
```
