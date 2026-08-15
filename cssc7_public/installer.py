"""CSSC installer. install the latest CSSC version from Lilias Hatterscheidt"""
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


def _log(msg: str) -> None:
    print(f"  {msg}")

def _major_of(v: str) -> str:
    m = re.search(r'(\d+)', str(v))
    return m.group(1) if m else '7'

def _read_manifest(here: Path) -> dict:
    mj = here / 'manifest.json'
    if mj.is_file():
        try:
            return json.loads(mj.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    return {}

def _ensure_on_path(d: str) -> None:
    if os.environ.get('CSSC_SKIP_PATH'):
        _log(f"(PATH update skipped; add manually: {d})")
        return
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0,
                                winreg.KEY_READ | winreg.KEY_WRITE) as k:
                try:
                    cur, _ = winreg.QueryValueEx(k, 'Path')
                except FileNotFoundError:
                    cur = ''
                parts = [p for p in cur.split(os.pathsep) if p]
                if any(p.lower() == d.lower() for p in parts):
                    return
                parts.append(d)
                winreg.SetValueEx(k, 'Path', 0, winreg.REG_EXPAND_SZ,
                                  os.pathsep.join(parts))
            _log(f"added to PATH: {d}   (open a NEW terminal to pick it up)")
        except Exception as e: 
            _log(f"could not edit PATH automatically — add manually: {d}  ({e})")
        return
    try:
        prof = Path.home() / '.profile'
        existing = prof.read_text(encoding='utf-8') if prof.exists() else ''
        if d not in existing:
            with open(prof, 'a', encoding='utf-8') as fh:
                fh.write(f'\n# CSSC\nexport PATH="{d}:$PATH"\n')
        _log(f"added to PATH via ~/.profile: {d}   (open a NEW terminal)")
    except OSError as e:
        _log(f"add to PATH manually: {d}  ({e})")


def install() -> None:
    here = Path(__file__).resolve().parent
    man = _read_manifest(here)
    version = str(man.get('version') or 'cssc7')
    major = str(man.get('major') or _major_of(version))
    base = Path(os.environ.get('LOCALAPPDATA') or str(Path.home())) / 'CSSC'
    root = base / f'cssc{major}'
    binlink = base / 'bin'
    print(f"Installing CSSC {version}  ->  {root}\n")
    if root.exists():
        _log(f"removing previous cssc{major} ...")
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    csscu = next((here / n for n in os.listdir(here) if n.endswith('.csscu')), None)
    if csscu is None or not csscu.is_file():
        raise FileNotFoundError('no .csscu payload found next to installer.py')
    _log(f"applying {csscu.name} ...")
    with zipfile.ZipFile(str(csscu)) as zf:
        for n in zf.namelist():
            if n == 'manifest.json':
                continue                        # already have it loose
            zf.extract(n, str(root))
    _log("installed toolchain payload (cssc.dll + tools)")
    if (here / 'python').is_dir():
        shutil.copytree(str(here / 'python'), str(root / 'python'),
                        dirs_exist_ok=True)
        _log("installed bundled Python 3.12")
    is_win = os.name == 'nt'
    bundled = root / 'python' / ('python.exe' if is_win else 'bin/python3')
    py = str(bundled) if bundled.exists() else sys.executable
    if not bundled.exists():
        _log(f"no bundled Python - launcher will use {py}")

    binlink.mkdir(parents=True, exist_ok=True)
    launch_py = root / 'cssc_launch.py'
    if is_win:
        launcher = binlink / 'cssc.bat'
        launcher.write_text(f'@echo off\r\n"{py}" "{launch_py}" %*\r\n',
                            encoding='utf-8')
    else:
        launcher = binlink / 'cssc'
        launcher.write_text(f'#!/bin/sh\nexec "{py}" "{launch_py}" "$@"\n',
                            encoding='utf-8')
        os.chmod(launcher, 0o755)
    _log(f"launcher -> {launcher}")
    _ensure_on_path(str(binlink))
    (root / 'VERSION').write_text(version, encoding='utf-8')
    print(f"\nCSSC {version} installed. Open a NEW terminal and run:  cssc --help")
if __name__ == '__main__':
    try:
        install()
    except Exception as e:
        print(f"\nInstall failed: {e}")
        sys.exit(1)
