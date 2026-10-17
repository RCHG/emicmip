#!/usr/bin/env python3
# ╭────────────────────────────────────────────────────────────────────────────╮
# │ cmip_config.py                                        (updated 2026-08)    │
# │                                                                            │
# │ Author:  Ramiro Checa-Garcia (KNMI)                                        │
# │ Purpose: Config file loading (TOML)                                        │
# │                                                                            │
# ╰────────────────────────────────────────────────────────────────────────────╯

import os
import sys

def expand_user(obj, source: str | None = None):
    """Replace "{user}" in every string of a config by the user running the tool.

    Lets one config serve every account, e.g. rawpath = "/hpcperm/{user}/raw_emissions/".
    The user comes from getpass.getuser() (USER/LOGNAME, else the system's user
    database), so it does not depend on the environment. Strings without "{user}"
    (fixed paths) are returned unchanged. When something is replaced, one line
    says so (with `source`, the config file, if given).
    """
    import getpass
    user = getpass.getuser()
    count = 0

    def sub(x):
        nonlocal count
        if isinstance(x, str):
            count += x.count("{user}")
            return x.replace("{user}", user)
        if isinstance(x, dict):
            return {k: sub(v) for k, v in x.items()}
        if isinstance(x, list):
            return [sub(v) for v in x]
        return x

    out = sub(obj)
    if count:
        import lib.aux as aux
        where = f" in {source}" if source else ""
        print(aux.pinfo(" Config  :  ") + f"{{user}} -> {user}{where} ({count} value{'s' if count > 1 else ''})")
    return out


def load_config(config_name: str, cmip_key: str) -> dict:
    """Load a TOML config file and return the section for one CMIP version.

    Args:
        config_name: path to the TOML config file (.toml)
        cmip_key: version key to select, case-insensitive (e.g. "cmip7";
            matched against the file's upper-cased top-level keys, "CMIP7")

    Returns:
        The config dict for that CMIP version, with "{user}" replaced (see expand_user).

    Raises:
        SystemExit: if `config_name`'s extension is not .toml
    """
    ext = os.path.splitext(config_name)[1].lower()
    if ext != ".toml":
        print(f"Unknown config format: {config_name} (only .toml is supported)")
        sys.exit(1)

    import tomllib
    with open(config_name, "rb") as f:
        return expand_user(tomllib.load(f)[cmip_key.upper()], source=config_name)
