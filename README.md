# ZAP

A lightweight Python virtual environment manager for Windows (ARM64 & x64) and Linux/macOS.

ZAP makes it easy to create, manage, and switch between Python virtual environments with multiple Python versions.

## Features

* **Cross-platform**: Works on Windows, Linux, macOS
* **Zero dependencies**: No extra packages needed
* **Multi-Python**: Handles multiple Python versions (including ARM64/x64 variants)
* **Clean organization**: All environments stored in one configurable root directory
* **Simple commands**: Easy to remember CLI with just what you need

## Installation

### Option 1: Install with pipx (Recommended)

This is the recommended method as it makes `zap` available system-wide without affecting your Python environment:

```bash
# From the directory containing zap.py and setup.py
pipx install .

# If you don't have pipx installed:
# On Windows: python -m pip install --user pipx
# On macOS: brew install pipx
# On Linux: python3 -m pip install --user pipx
```

After installation, the `zap` command will be available in any command prompt or PowerShell session.

### Option 2: Install with pip

Note: When installed with pip, `zap` will only be available in the Python environment where it was installed:

```bash
# System-wide installation (may require admin/sudo)
pip install .

# Or user-specific installation
pip install --user .
```

### Option 3: Run directly

Download `zap.py` and either:
- Run it directly: `python zap.py command`
- Make a wrapper script or batch file to add to your PATH

## Usage

```
# List available Python interpreters and environments
zap list

# Create a new environment
zap create 3.11 myproject

# Activate an environment (prints activation command)
zap activate myproject

# Activate an environment with a specific Python version
zap activate myproject --version 3.11

# Activate and spawn a new shell already activated
zap activate myproject --shell

# Delete an environment (with confirmation prompt)
zap delete myproject

# Delete an environment with a specific Python version
zap delete myproject --version 3.12-arm64

# Delete an environment (skip confirmation)
zap delete myproject --yes
```

### Environment Location

By default, environments are stored in:
- Windows: `C:\venvs\{python-version}\{env-name}`
- Linux/macOS: `~/venvs/{python-version}/{env-name}`

You can override this by setting the `ENV_ROOT` environment variable.

### Handling Multiple Environments

ZAP supports having environments with the same name but different Python versions.
When you try to activate or delete an environment and multiple matching ones are found:

1. ZAP will show you all matching environments with their respective Python versions
2. You'll be prompted to select the environment you want to use
3. You can avoid this prompt by specifying the Python version with the `--version` flag

Example:
```
$ zap activate myproject
Multiple environments named 'myproject' found:
  1. Python 3.11
  2. Python 3.12-arm64

Select an environment to activate (or Ctrl+C to cancel): 2
Selected: Python 3.12-arm64
& C:\venvs\3.12-arm64\myproject\Scripts\Activate.ps1
```

### Windows PowerShell Note

If you encounter issues with activation scripts on Windows PowerShell, you may need to adjust the execution policy:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## License

[MIT License](LICENSE)
