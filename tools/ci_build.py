"""Run a native build with a bounded failure annotation on the Actions page."""
from collections import deque
import json
from pathlib import Path
import subprocess
import sys


def escape(value):
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Pass the Python build script and its arguments")
    output = deque(maxlen=100)
    process = subprocess.Popen([sys.executable, *sys.argv[1:]], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, errors="replace")
    for line in process.stdout:
        print(line, end="", flush=True)
        output.append(line)
    code = process.wait()
    if code:
        detail = "".join(output)[-5000:]
        for path in sorted(Path("dist").glob("*smoke.json")):
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("error"):
                detail += "\n" + path.name + ": " + str(report["error"])[-3000:]
        print("::error title=Native build failure::" + escape(detail), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
