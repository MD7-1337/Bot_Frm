"""Run as a trusted assigned script with images/start.png in its project."""
from app.automation.api import Pattern, click, exists, getDevice, wait


def main():
    start = Pattern("start.png").similar(0.99).targetOffset(1, 0)
    if exists(start):
        point = click(start)
        print(f"{getDevice()}: clicked {point.x}, {point.y}")
    else:
        print(f"{getDevice()}: start target is absent; no tap sent")
    wait(0.05)


if __name__ == "__main__":
    main()
