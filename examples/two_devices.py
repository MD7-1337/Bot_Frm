"""Run two independent mock assignments; this example sends no Android input.

Run from the repository: python -m examples.two_devices
Real phones require backend='adb', their actual serials, and explicit approval.
Scripts execute with the current host user's privileges; there is no sandbox.
"""

import time

from app.automation import RuntimeCoordinator


def main() -> None:
    with RuntimeCoordinator(max_workers=2) as runtime:
        for serial, x in [("fixture-phone-one", 100), ("fixture-phone-two", 200)]:
            runtime.start(f"print(getDevice())\ntap({x}, 300)\nsleep(0.1)\nback()", serial, trusted=True, backend="mock")
        while True:
            for event in runtime.poll():
                print(event)
            if all(run.exitcode is not None for run in runtime.snapshot()):
                break
            time.sleep(0.02)
        for run in runtime.snapshot():
            print(run)


if __name__ == "__main__":
    main()
