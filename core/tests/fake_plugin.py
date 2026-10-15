"""A minimal plugin process for testing the client without a game.

Methods: handshake, observe, act (echoes), fail (JSON-RPC error), slow (sleeps), crash (exits).
"""

import json
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
        elif method == "crash":
            print("fatal: something broke", file=sys.stderr, flush=True)
            sys.exit(3)
        else:
            error = {"code": -32601, "message": f"Unknown method: {method}"}
            send({"jsonrpc": "2.0", "id": request_id, "error": error})


if __name__ == "__main__":
    main()
