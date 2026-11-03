#!/usr/bin/env python3
"""The steps and tools, on every system, without make: python run.py <step>; python run.py lists them. They're the
Makefile's targets, described in its comments."""
import os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = {"add-photos": "add_photos", "read-text": "read_text", "fit-cartridge": "fit_cartridge", "fit-label": "fit_label",
           "rectify": "rectify", "database": "build_database", "learn-choice": "learn_choice", "review-fits": "review_fits",
           "review-labels": "review_labels", "fit-by-hand": "fit_by_hand", "search-photos": "search_photos",
           "name-photos": "name_photos", "find-doubles": "find_doubles"}
CLEAN = {"clean-read-text": "generated/read-text", "clean-fit-cartridge": "generated/fit-cartridge", "clean-fit-label": "generated/fit-label",
         "clean-rectify": "generated/labels"}


def venv_python():
    return os.path.join(ROOT, ".venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join(ROOT, ".venv", "bin", "python")


def steps_help():
    with open(os.path.join(ROOT, "Makefile"), encoding="utf-8") as f:
        lines = [line[4:].rstrip() for line in f if line.startswith("#   ")]
    return "\n".join(("\n" if k and re.match(r"make ", l) else "") + re.sub(r"^make ", "python run.py ", l) for k, l in enumerate(lines))


def main(args):
    if not args:
        print(steps_help())
        return 0
    step, rest = args[0], args[1:]
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    if step == "setup":
        subprocess.run([sys.executable, "-m", "venv", os.path.join(ROOT, ".venv")], check=True)
        return subprocess.run([venv_python(), "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt")], cwd=ROOT).returncode
    if step in CLEAN:
        shutil.rmtree(os.path.join(ROOT, CLEAN[step]), ignore_errors=True)
        return 0
    if not os.path.exists(venv_python()):
        print("Run python run.py setup first.", file=sys.stderr)
        return 1
    if step == "test":
        return subprocess.run([venv_python(), "-m", "unittest", "discover", "-s", "src", "-p", "test_*.py"], cwd=ROOT, env=environment).returncode
    if step not in SCRIPTS:
        print(f"No step {step}. python run.py lists them.", file=sys.stderr)
        return 1
    return subprocess.run([venv_python(), os.path.join("src", SCRIPTS[step] + ".py")] + rest, cwd=ROOT, env=environment).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
