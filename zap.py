#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ZAP: Light-weight virtual-env manager for Windows (ARM64 & x64) and Linux/macOS.

Features
--------
* Enumerate installed Pythons via the Windows 'py' launcher (or PATH on *nix).
* Create, delete, list, and activate venvs; everything stored in one root dir.
* Zero third-party dependencies; works fine from any existing Python ≥3.7.

Notes
-----
* On Windows, PowerShell's ExecutionPolicy may block activation scripts.
  If you encounter this issue, run:
  `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`
* To make ZAP available from anywhere, either:
  1. Add this script to your PATH, or
  2. Create setup.py with entry_points and run `pip install .` or
  3. Use `pipx install .` from this directory
"""

import re, argparse, json, os, platform, shutil, subprocess, sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------- Configuration ----------
ENV_ROOT = Path(os.getenv("ENV_ROOT", str(Path.home() / "venvs") if os.name != "nt" else r"C:\venvs"))
ENV_ROOT.mkdir(parents=True, exist_ok=True)

# ---------- Helper functions ----------
def run(cmd: List[str]) -> Tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    return p.returncode, p.stdout.strip()

def installed_pythons() -> Dict[str, str]:
    """
    Returns { '3.11' : r'C:\\Python311\\python.exe', '3.12-arm64': r'C:\\…', … }
    Uses 'py -0p' on Windows; else scans PATH for 'pythonX.Y'.
    """
    versions = {}
    if os.name == "nt":
        rc, out = run(["py", "-0p"])
        pat = re.compile(r"-V:(?P<tag>[^\s*]+)\s+\*?\s*(?P<path>.+)")
        for line in out.splitlines():
            m = pat.search(line)
            if m:
                versions[m.group("tag")] = m.group("path").strip()
    else:
        # Fallback: look for python3.X executables in PATH
        for x in os.getenv("PATH", "").split(os.pathsep):
            for exe in Path(x).glob("python3.[0-9]"):
                rc, out = run([str(exe), "-c", "import sys,platform, json; print(json.dumps((sys.version_info[:2], platform.machine())))"])
                if rc == 0:
                    (major, minor), mach = json.loads(out)
                    versions[f"{major}.{minor}"] = str(exe)
    return versions

def envs_by_version() -> Dict[str, List[Path]]:
    """
    Get all environments organized by Python version.
    Returns a dict mapping Python version to list of environment paths.
    """
    envs = {}
    for ver_dir in ENV_ROOT.iterdir():
        if ver_dir.is_dir():
            envs[ver_dir.name] = [p for p in ver_dir.iterdir() if (p / "pyvenv.cfg").exists()]
    return envs

def find_envs_by_name(name: str, find_all: bool = True) -> List[Tuple[str, Path]]:
    """
    Find environments by name across all Python versions.
    
    Args:
        name: The environment name to search for
        find_all: If True, returns all matches. If False, stops after finding 2 matches.
                  This is an optimization when you only need to know if there are multiple matches.
    
    Returns:
        List of tuples (python_version, env_path) for all matching environments
    """
    matching_envs = []
    
    # Direct path approach - faster for checking specific env names
    for ver_dir in ENV_ROOT.iterdir():
        if not ver_dir.is_dir():
            continue
        
        # Check if this specific environment exists directly
        potential_env = ver_dir / name
        
        # Use faster Path.exists() check first, as pyvenv.cfg check is more expensive
        if potential_env.exists() and (potential_env / "pyvenv.cfg").exists():
            matching_envs.append((ver_dir.name, potential_env))
            
            # Optimization: if we only want to know if there are multiple matches
            # and we've already found 2, we can stop searching
            if not find_all and len(matching_envs) >= 2:
                break
    
    return matching_envs

def env_path(name: str, version: Optional[str] = None) -> Optional[Path]:
    """
    Find environment by name, optionally filtered by Python version.
    Returns the first matching environment or None if not found.
    If version is specified, only environments with that version are considered.
    If multiple environments have the same name but different versions and
    no version is specified, returns the first one found (unpredictable).
    """
    # If version is specified, look directly in that version's directory
    if version:
        env_dir = ENV_ROOT / version / name
        if env_dir.is_dir() and (env_dir / "pyvenv.cfg").exists():
            return env_dir
        return None
    
    # Otherwise, search all version directories (legacy behavior)
    for sub in ENV_ROOT.glob("*/*"):
        if sub.is_dir() and sub.name == name and (sub / "pyvenv.cfg").exists():
            return sub
    return None

def activate_cmd(env_dir: Path) -> str:
    if os.name == "nt":
        return fr"& {env_dir}\Scripts\Activate.ps1"
    return f"source {env_dir}/bin/activate"

def deactivate_cmd() -> str:
    # The deactivate command is the same for both PowerShell and bash
    # In PowerShell, 'deactivate' is a function that gets defined when activating
    return "deactivate"

def get_default_version() -> Optional[str]:
    config_path = Path.home() / ".zaprc"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("default_version="):
                    return line.strip().split("=", 1)[1]
    return None

def set_default_version(args):
    config_path = Path.home() / ".zaprc"
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(f"default_version={args.version}\n")
    print(f"Default Python version set to {args.version}")

def select_environment(matching_envs: List[Tuple[str, Path]], name: str, action_name: str):
    """
    Interactive UI for selecting between multiple environments with the same name.
    
    Args:
        matching_envs: List of tuples (python_version, env_path) for all matching environments
        name: The environment name
        action_name: The action being performed (e.g., "activate", "delete")
        
    Returns:
        Tuple of (selected_version, env_dir) or None if selection was cancelled/invalid
    """
    print(f"Multiple environments named '{name}' found:")
    for i, (ver, _) in enumerate(matching_envs, 1):
        print(f"  {i}. Python {ver}")
    
    # Ask user to select an option if we're in an interactive terminal
    if hasattr(sys.stdin, 'isatty') and sys.stdin.isatty():
        try:
            print(f"\nSelect an environment to {action_name} (or Ctrl+C to cancel):", end=" ")
            choice = input()
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(matching_envs):
                    selected_version, env_dir = matching_envs[choice_idx]
                    print(f"Selected: Python {selected_version}")
                    return selected_version, env_dir
                else:
                    print(f"Invalid selection. Please choose a number between 1 and {len(matching_envs)}.")
                    return None
            except ValueError:
                print("Invalid input. Please enter a number.")
                return None
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return None
    else:
        # If not in interactive terminal, show command examples
        print(f"\nPlease specify a version with --version or use the full command:")
        print(f"  zap {action_name} {name} --version VERSION")
        print(f"\nFor example:")
        print(f"  zap {action_name} {name} --version {matching_envs[0][0]}")
        return None

# ---------- Command implementations ----------
def cmd_list(_args):
    print(f"\n>> Available Python interpreters:")
    for ver, path in installed_pythons().items():
        print(f"  {ver:<9} -> {path}")
    
    print(f"\n>> Virtual environments in {ENV_ROOT}:")
    
    # Get environments and sort them numerically
    envs = envs_by_version()
    
    # Sort versions numerically - handle non-numeric parts gracefully
    def version_key(v):
        parts = []
        for part in re.split(r'[\.-]', v):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(float('inf'))  # Always pushes non-numeric to the end
        return tuple(parts)

    
    for ver in sorted(envs.keys(), key=version_key):
        env_list = envs[ver]
        if env_list:
            print(f"  Python {ver}")
            for env in sorted(env_list, key=lambda e: e.name):
                print(f"    * {env.name}")
    print()

def cmd_create(args):
    version = args.version
    if version is None:
        version = get_default_version()
        if not version:
            sys.exit("[!] No Python version specified and no default set. Use 'zap set-default <version>' or specify a version.")
    pythons = installed_pythons()
    if version not in pythons:
        sys.exit(f"[!] Python {version} not found. Run `zap list` first.")
    python_exe = pythons[version] # Get the full path to the python executable
    env_dir = ENV_ROOT / version / args.name
    if env_dir.exists():
        sys.exit(f"[!] Environment {args.name} already exists.")
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Creating venv at {env_dir} using {python_exe} ...")

    # Determine if we can use --upgrade-deps (Python 3.12+)
    venv_cmd = [python_exe, "-m", "venv"]
    
    # Check Python version to see if --upgrade-deps is supported (Python 3.12+)
    try:
        rc, out = run([python_exe, "-c", "import sys; print(sys.version_info >= (3, 12))"])
        if "True" in out:
            venv_cmd.append("--upgrade-deps")
    except Exception:
        # If version check fails, just proceed without --upgrade-deps
        pass
    
    venv_cmd.append(str(env_dir))
    
    try:
        rc, out = run(venv_cmd)
        if rc != 0:
            shutil.rmtree(env_dir, ignore_errors=True)
            sys.exit(out)
        print("Success!")
    except Exception as e:
        shutil.rmtree(env_dir, ignore_errors=True)
        sys.exit(f"Error creating environment: {e}")

def cmd_delete(args):
    # If a specific version is provided, look directly in that version's directory
    if args.version:
        env_dir = env_path(args.name, args.version)
        if not env_dir:
            sys.exit(f"[!] No environment named '{args.name}' with Python {args.version}")
    else:
        # No version specified, check for environments with this name
        matching_envs = find_envs_by_name(args.name)
        
        if not matching_envs:
            sys.exit(f"[!] No environment named '{args.name}'")
        elif len(matching_envs) > 1:
            # Multiple environments with the same name found
            # Use the helper function to handle selection
            selection = select_environment(matching_envs, args.name, "delete")
            if selection:
                _, env_dir = selection
            else:
                return  # User cancelled or invalid selection
        else:
            # Only one environment with this name
            env_dir = matching_envs[0][1]
            print(f"Using Python {matching_envs[0][0]} environment.")
    
    if not args.yes and input(f"Delete {env_dir}? [y/N] ").lower() != "y":
        return
    shutil.rmtree(env_dir)
    print("Done.")

def cmd_activate(args):
    # If a specific version is provided, look directly in that version's directory
    if args.version:
        env_dir = env_path(args.name, args.version)
        if not env_dir:
            sys.exit(f"[!] No environment named '{args.name}' with Python {args.version}")
    else:
        # No version specified, check for environments with this name
        matching_envs = find_envs_by_name(args.name)
        
        if not matching_envs:
            sys.exit(f"[!] No environment named '{args.name}'")
        elif len(matching_envs) > 1:
            # Multiple environments with the same name found
            # Use the helper function to handle selection
            selection = select_environment(matching_envs, args.name, "activate")
            if selection:
                _, env_dir = selection
            else:
                return  # User cancelled or invalid selection
        else:
            # Only one environment with this name
            env_dir = matching_envs[0][1]
            print(f"Using Python {matching_envs[0][0]} environment.")
    
    if not env_dir:
        version_msg = f" with Python {args.version}" if args.version else ""
        sys.exit(f"[!] No environment named '{args.name}'{version_msg}")
    
    cmd = activate_cmd(env_dir)
    
    # Always print the activation command
    print(cmd)
    
    # Execute the command if --shell flag is used or we're in an interactive terminal
    if args.shell:
        if os.name == "nt":
            subprocess.run(["powershell", "-NoExit", cmd])
        else:
            subprocess.run(["bash", "-c", cmd + "; exec bash"])
    elif hasattr(sys.stdout, 'isatty') and sys.stdout.isatty() and args.interactive:
        print("\nActivating environment...")
        if os.name == "nt":
            subprocess.run(["powershell", "-NoExit", cmd])
        else:
            subprocess.run(["bash", "-c", cmd + "; exec bash"])

def cmd_deactivate(_args):
    """Deactivate the current virtual environment if one is active."""
    # Check if a virtual environment is active by checking the VIRTUAL_ENV environment variable
    if "VIRTUAL_ENV" not in os.environ:
        print("No active virtual environment detected.")
        return
    
    # Get the active virtual environment path (we've verified it exists above)
    active_env = os.environ["VIRTUAL_ENV"]
    print(f"Deactivating environment: {Path(active_env).name}")
    
    # Get the deactivation command
    cmd = deactivate_cmd()
    
    # Execute the command
    if os.name == "nt":
        subprocess.run(["powershell", "-NoExit", cmd])
    else:
        subprocess.run(["bash", "-c", cmd + "; exec bash"])

# ---------- CLI ----------
parser = argparse.ArgumentParser(
    prog="zap",    description="""
ZAP: Minimal virtual environment manager for Python.

Commands:
  list                List available Python versions and created environments.
  create VERSION NAME Create a new venv using the given Python version tag.
  activate NAME       Print the activation command (or launch a shell with --shell).
                      When multiple envs share a name, offers interactive selection.
  deactivate          Deactivate the current virtual environment.
  delete NAME         Delete an existing virtual environment.
                      When multiple envs share a name, offers interactive selection.

Example:
  zap create 3.11 myenv
  zap activate myenv --shell
  zap activate myenv --version 3.11  # Explicitly specify Python version
  zap deactivate
  zap delete myenv -y
""",
    formatter_class=argparse.RawDescriptionHelpFormatter
)

sub = parser.add_subparsers(dest="cmd", required=True)

sub.add_parser("list", help="List Pythons and venvs").set_defaults(func=cmd_list)

p_create = sub.add_parser("create", help="Create a venv")
p_create.add_argument("version", nargs="?", help="Python tag e.g. 3.11 or 3.10-arm64 (optional if default set)")
p_create.add_argument("name", help="Environment name")
p_create.set_defaults(func=cmd_create)

p_delete = sub.add_parser("delete", help="Delete a venv")
p_delete.add_argument("name", help="Environment name")
p_delete.add_argument("--version", "-v", help="Python version of the environment (e.g., 3.11, 3.12-arm64)")
p_delete.add_argument("-y", "--yes", action="store_true", help="Skip deletion confirmation prompt")
p_delete.set_defaults(func=cmd_delete)

p_activate = sub.add_parser("activate", help="Show or start activation script")
p_activate.add_argument("name", help="Environment name")
p_activate.add_argument("--version", "-v", help="Python version of the environment (e.g., 3.11, 3.12-arm64)")
p_activate.add_argument("--shell", action="store_true", help="Spawn new shell already activated")
p_activate.add_argument("-i", "--interactive", action="store_true", help="Auto-activate if running in interactive terminal")
p_activate.set_defaults(func=cmd_activate)

p_deactivate = sub.add_parser("deactivate", help="Deactivate the current virtual environment")
p_deactivate.set_defaults(func=cmd_deactivate)

p_setdef = sub.add_parser("set-default", help="Set default Python version for new environments")
p_setdef.add_argument("version", help="Python tag e.g. 3.11 or 3.10-arm64")
p_setdef.set_defaults(func=set_default_version)

def main():
    try:
        args = parser.parse_args()
        args.func(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
