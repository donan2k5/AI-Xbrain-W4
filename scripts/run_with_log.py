import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_env(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            continue
        key, raw = value.split("=", 1)
        parsed[key] = raw
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a command and stream merged stdout/stderr to a UTF-8 log file.")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--hello", required=True)
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Missing command")

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(parse_env(args.env))

    with log_path.open("w", encoding="utf-8", buffering=1) as log_file:
        log_file.write(f"{args.hello}\n")
        log_file.write(f"cwd={args.cwd}\n")
        log_file.write(f"cmd={' '.join(command)}\n")
        log_file.flush()

        process = subprocess.Popen(
            command,
            cwd=args.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        assert process.stdout is not None
        for line in process.stdout:
            log_file.write(line)
        return process.wait()


if __name__ == "__main__":
    sys.exit(main())
