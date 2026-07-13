"""Docker-based code execution sandbox.

``DockerSandbox`` runs untrusted Python inside a throwaway container:
``--network=none`` (no net), ``--memory``/``--cpus`` caps, ``--rm`` auto-cleanup.
Pass it to ``PythonExecute(sandbox=...)`` to replace the default subprocess path.

Requires Docker on the host. Falls back is the caller's choice: the default
``PythonExecute`` still uses subprocess (for offline tests).
"""

from __future__ import annotations

import asyncio
from asyncio.subprocess import PIPE

from polyagent.tools.base import ToolResult


class DockerSandbox:
    def __init__(
        self,
        image: str = "python:3.12-slim",
        timeout: float = 30.0,
        network: bool = False,
        memory: str = "256m",
        cpus: str = "0.5",
    ) -> None:
        self.image = image
        self.timeout = timeout
        self.network = network
        self.memory = memory
        self.cpus = cpus

    async def run(self, code: str, timeout: float | None = None) -> ToolResult:
        to = timeout or self.timeout
        args: list[str] = ["docker", "run", "--rm"]
        if not self.network:
            args.append("--network=none")
        args += [f"--memory={self.memory}", f"--cpus={self.cpus}"]
        args += [self.image, "python", "-c", code]
        try:
            proc = await asyncio.create_subprocess_exec(*args, stdout=PIPE, stderr=PIPE)
        except FileNotFoundError as exc:
            return ToolResult(output=f"docker not found: {exc}", error=True)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=to)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(output=f"docker execution timed out after {to}s", error=True)
        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        ok = proc.returncode == 0
        body = out if ok else (err or out)
        return ToolResult(output=body, error=not ok, metadata={"returncode": proc.returncode})


class PathGuard:
    """Restrict file-tool paths to a whitelist of roots (prevents jailbreaks)."""

    def __init__(self, allowed_roots: list[str]) -> None:
        from pathlib import Path

        self._roots = [Path(r).resolve() for r in allowed_roots]

    def check(self, path: str) -> tuple[bool, str]:
        from pathlib import Path

        p = Path(path).resolve()
        for root in self._roots:
            try:
                p.relative_to(root)
                return True, str(p)
            except ValueError:
                continue
        return False, f"path {path} outside allowed roots"
