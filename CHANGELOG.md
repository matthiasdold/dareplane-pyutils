# Changelog

All notable changes to `dareplane_utils` are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are derived from git tags via `setuptools-scm`.

## [0.0.24]

### Breaking

- **`;` is now an obligatory message delimiter.** `DefaultServer` buffers incoming
  data and only dispatches a command once a `;` is found, so commands split across
  TCP segments are reassembled correctly. Clients that did not terminate messages
  with `;` will now hang in the buffer instead of being handled.
  `ModuleConnection` appends the delimiter automatically.
- **Positional arguments to PCOMMs are no longer supported.** A message is either a
  bare `PCOMM` or `PCOMM|{"key": value}` with a single JSON *object* of keyword
  arguments. More than one `|` payload, or a JSON payload that is not an object, is
  rejected and mapped onto a noop. This was never the documented behaviour.
- **`GET_PCOMMS` now advertises the built-in commands.** The response includes
  `STOP`, `CLOSE`, `GET_PCOMMS` and `UP` alongside the entries of `pcommand_map`,
  where it previously listed only `STOP` and `CLOSE`.

### Added

- `dareplane_utils.__version__`, resolved from install metadata.
- Configurable `delimiter` (default `b";"`) on `DefaultServer`.
- Idle/accept timeout for incoming connections, so a server waiting for a client
  can still be stopped.

### Changed

- Callback threads are now bound to the TCP connection that created them and the
  callback stack is cleared on connection loss and reconnect, so a reconnecting
  client no longer inherits stale callbacks.
- Shutdown signals the stop event before closing sockets, fixing a race between
  callback threads and connection teardown.
- Threads and processes are snapshotted before being killed or removed, making
  book-keeping robust when a callback exits during teardown.
- `UP` health-check messages are no longer logged, and are accepted with or without
  a trailing newline or pipe, matching the other PCOMMs.
- Connection failures against a dead host process raise a specific
  `ConnectionRefusedError` instead of a generic connection error.

### Fixed

- Race condition between callback threads and connection closing.
- Stop event not being honoured by the default server(s).
- Eager check for an existing network handler removed; it could reject valid setups.

### Internal

- Versioning migrated to `setuptools-scm`: the git tag is the single source of
  truth, `pyproject.toml` carries no static version, and the publish workflow
  checks out with `fetch-depth: 0`.
- Ruff configuration and lint fixes across the package.
- Substantially expanded test suite: message framing, callback server behaviour,
  delimiter handling, log capture, and daemon threads for teardown.
- Documentation improvements in the README and API reference.

## [0.0.23] - previous release

See the GitHub release notes for versions up to and including `0.0.23`.

[Unreleased]: https://github.com/matthiasdold/dareplane-pyutils/compare/v0.0.23...HEAD
[0.0.23]: https://github.com/matthiasdold/dareplane-pyutils/releases/tag/v0.0.23
