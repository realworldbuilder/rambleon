import subprocess

from rambleon import doctor
from rambleon.paths import Paths


def test_doctor_asks_the_ai_only_when_told_to(tmp_path, monkeypatch):
    paths = Paths(repo_root=tmp_path, wow_dir=None, archive_dir=tmp_path / "archive", exports_dir=tmp_path / "exports")
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "1.0", "")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(doctor.subprocess, "run", run)

    def no_launchctl():
        raise FileNotFoundError("launchctl")
    monkeypatch.setattr("rambleon.service.is_loaded", no_launchctl)
    checks = {c.label: c for c in doctor.run_doctor(paths)}
    assert not any("-p" in c for c in calls) and "login not checked" in checks["Claude CLI"].detail
    assert checks["Watcher"].status != "RUNNING"        # and no crash on a machine without launchctl
    doctor.run_doctor(paths, check_ai=True)
    assert any("-p" in c for c in calls)
