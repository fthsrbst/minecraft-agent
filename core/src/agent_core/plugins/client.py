"""Starts a plugin as a child process and talks to it over newline-delimited JSON-RPC on stdio.

stdout carries protocol messages only; the plugin's stderr is forwarded to this process's log.
Requests are matched to responses by id, so several can be in flight at once. `event`
notifications from the plugin are queued and read with `next_event`.
"""

import asyncio
import contextlib
import logging
import os
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Self

from agent_core.plugins.jsonrpc import (
    PROTOCOL_VERSION,
    JsonObject,
    JsonValue,
    decode_message,
    encode_request,
)
from agent_core.plugins.manifest import PluginManifest, load_manifest

DEFAULT_TIMEOUT_S = 10.0
# Joining a game can take a while on a cold server.
HANDSHAKE_TIMEOUT_S = 90.0
# asyncio's default 64 KiB line limit is too small for large observations.
MAX_LINE_BYTES = 16 * 1024 * 1024
STDERR_TAIL_LINES = 20
# Events nobody reads must not grow memory without bound; the oldest are dropped first.
MAX_QUEUED_EVENTS = 1000
# Variables every child process needs to run at all. Everything else (API keys, passwords) is
# passed only when the manifest lists it for that component, so secrets reach no process by default.
BASE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "TEMP", "TMP")


class PluginError(Exception):
    """Base class for errors talking to a plugin."""


class PluginRpcError(PluginError):
    """The plugin answered a request with a JSON-RPC error."""

    def __init__(self, method: str, code: int, message: str, data: JsonValue = None) -> None:
        super().__init__(f"{method} failed ({code}): {message}")
        self.method = method
        self.code = code
        self.rpc_message = message
        self.data = data


class PluginExitedError(PluginError):
    """The plugin process ended; pending and later requests fail with this."""


class PluginClient:
    def __init__(self, manifest: PluginManifest, process: asyncio.subprocess.Process) -> None:
        self.manifest = manifest
        self._process = process
        self._log = logging.getLogger(f"agent_core.plugins.{manifest.id}")
        self._next_id = 1
        self._pending: dict[int, tuple[str, asyncio.Future[JsonValue]]] = {}
        self._events: asyncio.Queue[JsonObject] = asyncio.Queue(maxsize=MAX_QUEUED_EVENTS)
        self._stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._exit_error: PluginExitedError | None = None
        self._closing = False
        self._readers = [
            asyncio.create_task(self._read_stdout(), name=f"{manifest.id}-stdout"),
            asyncio.create_task(self._read_stderr(), name=f"{manifest.id}-stderr"),
        ]

    @classmethod
    async def start(
        cls,
        plugin_dir: Path,
        *,
        component: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Self:
        """Starts the plugin's main process, or one of its named `components`.

        The child sees only `BASE_ENV` plus the variables its manifest entry lists, taken from
        `env` (default: this process's environment).
        """
        manifest = load_manifest(plugin_dir)
        source = os.environ if env is None else env
        allowed = (*BASE_ENV, *manifest.env_for(component))
        process = await asyncio.create_subprocess_exec(
            *manifest.command_for(component),
            cwd=manifest.directory,
            env={name: source[name] for name in allowed if name in source},
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=MAX_LINE_BYTES,
        )
        return cls(manifest, process)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    async def request(
        self, method: str, params: JsonObject | None = None, *, timeout_s: float = DEFAULT_TIMEOUT_S
    ) -> JsonValue:
        if self._exit_error is not None:
            raise self._exit_error
        if self._closing:
            raise PluginError(f"{self.manifest.id}: the client is closed.")
        stdin = self._process.stdin
        if stdin is None:  # pragma: no cover - start() always opens the pipes
            raise PluginError("Plugin stdin is not a pipe.")

        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[JsonValue] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (method, future)
        try:
            # The write is inside the timeout too: a plugin that stops reading stdin fills the pipe.
            async with asyncio.timeout(timeout_s):
                stdin.write(encode_request(request_id, method, params or {}))
                await stdin.drain()
                return await future
        except TimeoutError:
            raise TimeoutError(
                f"{self.manifest.id}: {method} got no answer within {timeout_s:g} s."
            ) from None
        except (BrokenPipeError, ConnectionResetError):
            raise self._exited() from None
        finally:
            self._pending.pop(request_id, None)

    async def handshake(self, *, timeout_s: float = HANDSHAKE_TIMEOUT_S) -> JsonObject:
        result = await self.request(
            "handshake", {"protocolVersion": PROTOCOL_VERSION}, timeout_s=timeout_s
        )
        return self._expect_object("handshake", result)

    async def observe(self) -> JsonObject:
        return self._expect_object("observe", await self.request("observe"))

    async def act(
        self,
        primitive: str,
        args: JsonObject | None = None,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> JsonObject:
        result = await self.request(
            "act", {"primitive": primitive, "args": args or {}}, timeout_s=timeout_s
        )
        return self._expect_object("act", result)

    async def next_event(self, timeout_s: float) -> JsonObject:
        """Waits for the next game event; raises TimeoutError if none arrives in time."""
        async with asyncio.timeout(timeout_s):
            return await self._events.get()

    def drain_events(self) -> list[JsonObject]:
        """Returns all queued events without waiting."""
        events: list[JsonObject] = []
        while not self._events.empty():
            events.append(self._events.get_nowait())
        return events

    async def close(self, timeout_s: float = 5.0) -> None:
        """Asks the plugin to stop (closes stdin, then SIGTERM), and kills it if it does not."""
        self._closing = True
        if self._process.returncode is None:
            if self._process.stdin is not None and not self._process.stdin.is_closing():
                self._process.stdin.close()
            try:
                async with asyncio.timeout(timeout_s):
                    await self._process.wait()
            except TimeoutError:
                self._log.warning("plugin did not exit after stdin closed; terminating")
                self._process.terminate()
                try:
                    async with asyncio.timeout(timeout_s):
                        await self._process.wait()
                except TimeoutError:
                    self._log.error("plugin ignored SIGTERM; killing")
                    self._process.kill()
                    await self._process.wait()
        for task in self._readers:
            task.cancel()
        for task in self._readers:
            # A reader that already failed was logged in _read_stdout; close() must still finish.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._fail_pending(self._exited())

    def _expect_object(self, method: str, result: JsonValue) -> JsonObject:
        if not isinstance(result, dict):
            raise PluginError(
                f"{self.manifest.id}: {method} returned {type(result).__name__}, not an object."
            )
        return result

    def _exited(self) -> PluginExitedError:
        if self._exit_error is None:
            tail = "\n".join(self._stderr_tail) or "(no stderr output)"
            self._exit_error = PluginExitedError(
                f"{self.manifest.id} plugin exited (code {self._process.returncode}). "
                f"Last stderr lines:\n{tail}"
            )
        return self._exit_error

    def _fail_pending(self, error: PluginError) -> None:
        for _, future in self._pending.values():
            if not future.done():
                future.set_exception(error)

    async def _read_stdout(self) -> None:
        stdout = self._process.stdout
        if stdout is None:  # pragma: no cover - start() always opens the pipes
            return
        try:
            while line := await stdout.readline():
                message = decode_message(line)
                if message is None:
                    self._log.warning("ignoring non-protocol stdout line: %r", line[:200])
                    continue
                self._dispatch(message)
        except Exception:
            # An unreadable stream (e.g. a line over MAX_LINE_BYTES) means the protocol is broken;
            # stop the plugin instead of leaving every request to wait for its timeout.
            self._log.exception("plugin stdout is unreadable; stopping the plugin")
            if self._process.returncode is None:
                self._process.kill()
        # stdout closed: the plugin is gone. Wait for the exit code so the error can report it.
        await self._process.wait()
        self._fail_pending(self._exited())

    def _dispatch(self, message: JsonObject) -> None:
        request_id = message.get("id")
        if "method" in message and request_id is None:
            if message["method"] == "event" and isinstance(params := message.get("params"), dict):
                if self._events.full():
                    self._events.get_nowait()
                    self._log.warning("event queue full; dropped the oldest event")
                self._events.put_nowait(params)
            else:
                self._log.warning("ignoring unknown notification: %s", message.get("method"))
            return
        # bool is a subclass of int in Python; `true` must not match request 1.
        if (
            isinstance(request_id, bool)
            or not isinstance(request_id, int)
            or request_id not in self._pending
        ):
            self._log.warning("ignoring response with unknown id: %r", request_id)
            return

        method, future = self._pending[request_id]
        if future.done():  # the request already timed out
            return
        error = message.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            text = error.get("message")
            future.set_exception(
                PluginRpcError(
                    method,
                    code if isinstance(code, int) else -32603,
                    text if isinstance(text, str) else "unknown error",
                    error.get("data"),
                )
            )
        else:
            future.set_result(message.get("result"))

    async def _read_stderr(self) -> None:
        stderr = self._process.stderr
        if stderr is None:  # pragma: no cover - start() always opens the pipes
            return
        while line := await stderr.readline():
            text = line.decode(errors="replace").rstrip()
            self._stderr_tail.append(text)
            self._log.info("%s", text)
