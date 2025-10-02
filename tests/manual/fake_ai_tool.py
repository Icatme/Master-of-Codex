"""A simple interactive script that simulates an AI coding CLI."""
from __future__ import annotations

import sys
import time


def main() -> None:
    sys.stdout.write("Fake AI tool ready for instructions.\n")
    sys.stdout.flush()

    for line in sys.stdin:
        command = line.rstrip("\r\n")
        if not command:
            continue

        sys.stdout.write("Processing request...\n")
        sys.stdout.flush()
        time.sleep(0.2)

        sys.stdout.write("Working on task details.\n")
        sys.stdout.flush()
        time.sleep(0.2)

        sys.stdout.write("Task checkpoint reached.\n")
        sys.stdout.flush()
        time.sleep(0.2)

        sys.stdout.write("READY_FOR_NEXT_STEP\n")
        sys.stdout.flush()
        break

    sys.stdout.write("Shutting down fake AI tool.\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
