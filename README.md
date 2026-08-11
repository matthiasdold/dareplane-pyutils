# Dareplane Python Utils

This module includes utilities for python which are used within the dareplane
framework. It contains functionality which shared can be reused within multiple modules.
This currently includes:

1. A `DefaultServer` - which will be loaded an extended within each module to implement the dareplane API
1. `logging` - which contains the standard formatting and a SocketHandler which is modified to send `json` representations of the logging records to the default logging server port (9020). This is used to enable cross process logging.
1. A `StreamWatcher` implementation - which is a utility class to query a single LSL stream into a ring buffer.
1. A `ModuleConnection` - which, together with a `launcher` and `communicator`, is used to launch and interact with other modules (currently supports launching Python and .exe programs).

## Default Dareplane Server

This default server is used by all `Dareplane` python modules as a starting
point for their `TCP` socket. The idea is to have a single source for common
functionality and patch everything that is model specific on top of this

### Functional incarnations

Currently we are faced with two functional incarnations of servers

1. Spawning functionality from the server in a separate thread, being linked via events to the
   main thread (usually the server).
2. Spawning a subprocess for running functionality - Currently necessary for running `psychopy` as it cannot be run from outside the main thread.

### The TCP command protocol

#### Framing

**Every command must be terminated by a `;`.** TCP is a byte stream without message
boundaries, so a single `recv` can return half a command or several concatenated ones. The
server therefore buffers incoming bytes and only dispatches a command once it sees the
delimiter. A command without a trailing `;` stays in the buffer and is *never* executed - it
waits for the rest of the message to arrive.

```python
sock.sendall(b"MYCOMMAND;")               # dispatched
sock.sendall(b"CMD_A;CMD_B;CMD_C;")       # all three dispatched, in order
sock.sendall(b"MYCOMMAND")                # buffered, nothing happens
```

Empty segments and pure whitespace between delimiters are ignored, so `;;CMD;` is fine.

If you connect via `ModuleConnection`, this is handled for you - `send_message` appends the
delimiter when it is missing:

```python
conn.send_message(b"UP")    # b"UP;" goes on the wire
```

#### Command syntax

Commands are `|`-separated. The **last** segment is always parsed as a JSON object of keyword
arguments, any segments in between are passed as positional strings:

| sent | resulting call |
| --- | --- |
| `CMD;` | `func()` |
| `CMD\|{"a": 1};` | `func(a=1)` |
| `CMD\|pos1\|{};` | `func("pos1")` |
| `CMD\|pos1\|{"b": 2};` | `func("pos1", b=2)` |

Because the trailing segment is always treated as JSON, a single positional argument needs an
explicit empty object: `CMD|pos1|{};`. Sending `CMD|pos1;` fails to decode and the message is
logged as an error and dropped.

#### Built-in commands

These are handled by every server before the module specific `pcommand_map` is consulted:

| command | effect |
| --- | --- |
| `STOP;` | stop all threads and subprocesses spawned by this module |
| `CLOSE;` | stop listening and shut the server down |
| `UP;` | health check, replies with `1` |
| `GET_PCOMMS;` | replies with a `\|`-separated list of available commands, including `STOP` and `CLOSE` |

Any other command is looked up in `pcommand_map`; unknown commands are logged as a warning
and otherwise ignored.

#### Defaults

`DefaultServer` is a dataclass - all of the below are constructor arguments:

| field | default | meaning |
| --- | --- | --- |
| `port` | `8080` | port the server binds to |
| `ip` | `"0.0.0.0"` | interface the server binds to |
| `nlisten` | `10` | backlog of queued connections |
| `name` | `"default_server"` | used in the connection banner `Connected to <name>` |
| `delimiter` | `b";"` | command terminator used for framing |
| `msg_interpreter` | `interpret_msg` | maps a parsed command onto a `pcommand_map` entry |
| `thread_stopper` | `stop_thread` | how spawned threads are joined on `STOP`/shutdown |
| `proc_stopper` | `stop_process` | how spawned subprocesses are terminated |
| `pcommand_map` | `{}` | the module specific `command -> callable` mapping |

The default logging server port is `9020` (see the Logging section below).

Handlers registered in `pcommand_map` must return one of:

- an `int` - fire and forget, nothing is tracked,
- a `tuple[threading.Thread, threading.Event]` - the server tracks the thread and sets the
  event on `STOP`,
- a `subprocess.Popen` - the server tracks and terminates the process on `STOP`.

Anything else raises `UnknownMsgInterpretation`.

```python
from dareplane_utils.default_server.server import DefaultServer

server = DefaultServer(port=8080, name="my_module")
server.pcommand_map = {"MYCOMMAND": my_handler}
server.init_server()
server.start_listening()
```

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

## Event Loop

A class that implements a custom event loop with precise timing.

The EventLoop uses dareplane_utils.general.time.sleep_s for more precise
sleep timing at the expense of CPU usage.

Callbacks are the means of interacting with the event loop. There are two types of callbacks:

- Periodic callbacks: These are executed at regular intervals.
- One-time callbacks: These are executed once and then removed from the list of callbacks.
  One-time callback can furthermore be scheduled to run at a specific time in the future.

Callbacks can be any callable function, which gets one and only one argument, which is
a context object, that can be of type any. This ensures that any type of input can
be implemented.

```python

def no_arg_callback():
    print("Running with no args")

evloop = EventLoop(dt_s=0.1)  # process callbacks every 100ms

# for a callback with no args we use lambda to blank the callback arg
evloop.add_callback_once(lambda ctx: no_arg_callback())
```

## Building the documentation

The API reference is generated from the docstrings with
[quartodoc](https://machow.github.io/quartodoc/) and rendered by
[quarto](https://quarto.org/) (which has to be installed separately).

```bash
uv pip install -e ".[docs]"
python -m quartodoc build   # regenerate reference/ and _sidebar.yml from _quarto.yml
quarto render               # render the site into _site/
```

`reference/`, `objects.json` and `_site/` are generated output and are gitignored -
`_sidebar.yml` is the only build product that is tracked, so re-run `quartodoc build`
whenever sections are added to `_quarto.yml`.

Note that quartodoc cannot render the numpy `Methods` docstring section - it generates a
methods table from the class members itself, so list methods in a `Notes` section instead if
they need extra explanation.

## TODO

- [ ] channel names are only initialized on connection
