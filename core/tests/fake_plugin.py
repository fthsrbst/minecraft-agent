"""A minimal plugin process for testing the client without a game.

Methods: handshake, observe, act (echoes), fail (JSON-RPC error), slow (sleeps), crash (exits).
"""

import json
import os
import sys
import time


def send(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    print("fake plugin started", file=sys.stderr, flush=True)
    sys.stdout.write("this line is not JSON-RPC\n")
    sys.stdout.flush()
    for line in sys.stdin:
        request = json.loads(line)
        request_id, method = request["id"], request["method"]
        params = request.get("params", {})
        if method == "handshake":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"plugin": {"id": "fake"}}})
            send({"jsonrpc": "2.0", "method": "event", "params": {"type": "ready"}})
        elif method == "observe":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"position": {"x": 1}}})
        elif method == "act":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"echo": params}})
        elif method == "fail":
            error = {"code": -32001, "message": "not ready", "data": {"retry": True}}
            send({"jsonrpc": "2.0", "id": request_id, "error": error})
        elif method == "slow":
            time.sleep(float(params["seconds"]))
            send({"jsonrpc": "2.0", "id": request_id, "result": "slow done"})
        elif method == "garbage":
            # Not UTF-8: the client must skip the line, not lose its reader.
            sys.stdout.buffer.write(b"\xff\xfe not utf-8\n")
            sys.stdout.flush()
            send({"jsonrpc": "2.0", "id": request_id, "result": "after garbage"})
        elif method == "env":
            send({"jsonrpc": "2.0", "id": request_id, "result": dict(os.environ)})
        elif method == "spam_events":
            for n in range(int(params["n"])):
                send({"jsonrpc": "2.0", "method": "event", "params": {"n": n}})
            send({"jsonrpc": "2.0", "id": request_id, "result": "spammed"})
        elif method == "bool_id":
            send({"jsonrpc": "2.0", "id": True, "result": "wrong"})
        elif method == "skill.run":
            code = params["code"]
            run_id = f"run-{request_id}"
            send({"jsonrpc": "2.0", "id": request_id, "result": {"runId": run_id}})
            if code == "hang":
                pass  # never reports done; the core must cancel
            else:
                status = "error" if code == "fail" else "ok"
                done = {
                    "type": "skill.done",
                    "runId": run_id,
                    "status": status,
                    "result": {"args": params["args"]},
                    "error": "boom" if status == "error" else None,
                    "durationMs": 12,
                    "primitiveCalls": 3,
                    "logs": ["started", "finished"],
                }
                send({"jsonrpc": "2.0", "method": "event", "params": done})
        elif method == "skill.cancel":
            print(f"cancelled {params.get('runId')}", file=sys.stderr, flush=True)
            send({"jsonrpc": "2.0", "id": request_id, "result": {"cancelled": True}})
        elif method == "crash":
            print("fatal: something broke", file=sys.stderr, flush=True)
            sys.exit(3)
        else:
            error = {"code": -32601, "message": f"Unknown method: {method}"}
            send({"jsonrpc": "2.0", "id": request_id, "error": error})


if __name__ == "__main__":
    main()
