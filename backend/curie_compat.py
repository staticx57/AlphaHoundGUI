"""
Make Curie usable from a web server.

Curie keeps its nuclear data in SQLite files and opens one connection per file, in a module-level dictionary, the first time
any thread asks for data. sqlite3 refuses to use a connection from another thread by default, and FastAPI answers requests
from a pool of threads, so a Curie lookup worked or raised "SQLite objects created in a thread can only be used in that same
thread" depending on which worker happened to run it (the first request after start-up worked, the next one often did not).

make_curie_thread_safe() opens Curie's connections with check_same_thread=False; the data files are only ever read, and callers
that look things up (decay_engine) also hold CURIE_LOCK so two threads never run a cursor on the shared connection at once.
"""

import sqlite3
import threading

CURIE_LOCK = threading.RLock()


class _Sqlite3Shim:
    """The sqlite3 module, except that connect() allows use from any thread."""

    def __getattr__(self, name):
        return getattr(sqlite3, name)

    @staticmethod
    def connect(*args, **kwargs):
        kwargs.setdefault("check_same_thread", False)
        return sqlite3.connect(*args, **kwargs)


def make_curie_thread_safe(curie_module) -> bool:
    """Patch Curie's data module (once). Returns True if the patch is in place."""
    data = getattr(curie_module, "data", None)
    if data is None or not hasattr(data, "sqlite3"):
        return False
    if getattr(data, "_radtrace_threadsafe", False):
        return True
    data.sqlite3 = _Sqlite3Shim()
    connections = getattr(data, "GLOB_CONNECTIONS_DICT", None)
    if isinstance(connections, dict):
        for connection in list(connections.values()):
            try:
                connection.close()
            except Exception:
                pass
        connections.clear()                      # reopen them with the flag set
    data._radtrace_threadsafe = True
    return True
