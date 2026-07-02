from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from sysconfig import get_path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_executable(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def _run(command: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _documented_commands() -> list[str]:
    readme = README.read_text(encoding="utf-8")
    commands = sorted(set(re.findall(r"^rtl-agent ([a-z][a-z-]+)\b", readme, re.MULTILINE)))
    if not commands:
        raise RuntimeError("README does not document any rtl-agent subcommands")
    return commands


def main() -> int:
    if shutil.which("python3") is None and not Path(sys.executable).exists():
        print("error: no Python executable available", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="rtl-agent-packaging-smoke-") as tmp:
        tmp_path = Path(tmp)
        wheel_dir = tmp_path / "wheels"
        wheel_dir.mkdir()
        build = _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheel_dir),
                str(ROOT),
            ]
        )
        if build.returncode != 0:
            sys.stderr.write(build.stdout)
            sys.stderr.write(build.stderr)
            return build.returncode

        wheels = sorted(wheel_dir.glob("rtl_agent-*.whl"))
        if len(wheels) != 1:
            print(f"error: expected exactly one rtl-agent wheel, found {wheels}", file=sys.stderr)
            return 2

        venv_dir = tmp_path / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = _venv_python(venv_dir)
        rtl_agent = _venv_executable(venv_dir, "rtl-agent")

        install = _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(wheels[0]),
            ]
        )
        if install.returncode != 0:
            sys.stderr.write(install.stdout)
            sys.stderr.write(install.stderr)
            return install.returncode

        site_packages = Path(
            subprocess.check_output(
                [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                text=True,
            ).strip()
        )
        current_site_packages = get_path("purelib")
        (site_packages / "rtl_agent_packaging_smoke_deps.pth").write_text(
            current_site_packages + "\n",
            encoding="utf-8",
        )

        checks = [
            [str(rtl_agent), "--help"],
            [str(python), "-m", "rtl_agent", "--help"],
        ]
        checks.extend([str(rtl_agent), command, "--help"] for command in _documented_commands())

        for command in checks:
            result = _run(command)
            if result.returncode != 0:
                sys.stderr.write(result.stdout)
                sys.stderr.write(result.stderr)
                return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
