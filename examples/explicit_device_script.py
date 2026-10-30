"""The worker injects device; it is bound to this run's assigned serial."""
from app.automation.api import Pattern


def main():
    target = device.waitImage(Pattern("start.png").similar(0.99), timeout=2)
    point = device.click(target)
    print(f"{device.serial}: {device.getResolution()}, target={point}")


if __name__ == "__main__":
    main()
