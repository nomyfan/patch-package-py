import subprocess
import sys
import tempfile

import pytest

from patch_package_py.core import (
    Resolver,
    apply_patch,
    commit_changes,
    find_site_packages,
    prepare_patch_workspace,
    venv_python,
)

PACKAGE = "six"
PACKAGE_VERSION = "1.16.0"


def _make_mock_mkdtemp(target_dir):
    def mock_mkdtemp(*args, **kwargs):
        target_dir.mkdir(exist_ok=True)
        return str(target_dir)

    return mock_mkdtemp


@pytest.fixture()
def project(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    target_env = project_dir / ".venv"
    subprocess.check_call(["uv", "venv", str(target_env), "--python", sys.executable])
    subprocess.check_call(
        [
            "uv",
            "pip",
            "install",
            "--no-deps",
            f"{PACKAGE}=={PACKAGE_VERSION}",
            "--python",
            str(venv_python(target_env)),
        ]
    )

    resolver = Resolver()
    module_path, version = resolver.resolve_in_venv(target_env, PACKAGE)
    assert version == PACKAGE_VERSION

    return {
        "dir": project_dir,
        "target_env": target_env,
        "module_path": module_path,
        "version": version,
    }


class TestCarryOverPatchE2E:
    def test_new_workspace_has_existing_patch_applied(
        self, tmp_path, monkeypatch, project
    ):
        module_path = project["module_path"]
        version = project["version"]
        target_env = project["target_env"]

        # Workspace 1: create and commit a patch
        ws1 = tmp_path / "ws1"
        monkeypatch.setattr(tempfile, "mkdtemp", _make_mock_mkdtemp(ws1))
        prepare_patch_workspace(module_path, PACKAGE, version, target_env)

        ws1_sp = find_site_packages(ws1 / "venv")
        six_py = ws1_sp / "six.py"
        original = six_py.read_text()
        six_py.write_text(original + "\n# patched by e2e test\n")

        commit_changes(PACKAGE, version, ws1_sp, target_env)

        patch_file = project["dir"] / "patches" / f"{PACKAGE}+{version}.patch"
        assert patch_file.exists()

        # Workspace 2 with amend: should carry over the patch
        ws2 = tmp_path / "ws2"
        monkeypatch.setattr(tempfile, "mkdtemp", _make_mock_mkdtemp(ws2))
        prepare_patch_workspace(module_path, PACKAGE, version, target_env, amend=True)

        ws2_sp = find_site_packages(ws2 / "venv")
        assert "# patched by e2e test" in (ws2_sp / "six.py").read_text()

        diff = subprocess.check_output(
            ["git", "diff", "--relative"], cwd=ws2_sp, text=True
        )
        assert "patched by e2e test" in diff

    def test_default_is_clean(self, tmp_path, monkeypatch, project):
        module_path = project["module_path"]
        version = project["version"]
        target_env = project["target_env"]

        # Workspace 1: create and commit a patch
        ws1 = tmp_path / "ws1"
        monkeypatch.setattr(tempfile, "mkdtemp", _make_mock_mkdtemp(ws1))
        prepare_patch_workspace(module_path, PACKAGE, version, target_env)

        ws1_sp = find_site_packages(ws1 / "venv")
        six_py = ws1_sp / "six.py"
        original = six_py.read_text()
        six_py.write_text(original + "\n# should not appear\n")

        commit_changes(PACKAGE, version, ws1_sp, target_env)

        # Workspace 2 without --amend: should NOT have the patch
        ws2 = tmp_path / "ws2"
        monkeypatch.setattr(tempfile, "mkdtemp", _make_mock_mkdtemp(ws2))
        prepare_patch_workspace(module_path, PACKAGE, version, target_env)

        ws2_sp = find_site_packages(ws2 / "venv")
        assert "# should not appear" not in (ws2_sp / "six.py").read_text()

        diff = subprocess.check_output(
            ["git", "diff", "--relative"], cwd=ws2_sp, text=True
        )
        assert diff == ""

    def test_amend_with_bad_patch_recovers_to_clean_state(
        self, tmp_path, monkeypatch, project
    ):
        module_path = project["module_path"]
        version = project["version"]
        target_env = project["target_env"]

        # Write a corrupt patch file
        patches_dir = project["dir"] / "patches"
        patches_dir.mkdir()
        patch_file = patches_dir / f"{PACKAGE}+{version}.patch"
        patch_file.write_text(
            "--- a/six.py\n"
            "+++ b/six.py\n"
            "@@ -1,3 +1,3 @@\n"
            " this context does not exist in six.py\n"
            "-nor does this line\n"
            "+so the patch will fail\n"
        )

        ws = tmp_path / "ws"
        monkeypatch.setattr(tempfile, "mkdtemp", _make_mock_mkdtemp(ws))
        prepare_patch_workspace(module_path, PACKAGE, version, target_env, amend=True)

        ws_sp = find_site_packages(ws / "venv")
        git_path = ws_sp.parent

        # No modified or staged files
        diff = subprocess.check_output(
            ["git", "diff", "--relative"], cwd=ws_sp, text=True
        )
        assert diff == ""

        # No untracked files (.rej, etc.)
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=git_path,
            text=True,
        )
        assert untracked == ""

        # No ignored residue
        ignored = subprocess.check_output(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard"],
            cwd=git_path,
            text=True,
        )
        assert ignored == ""


class TestRestoreApplyE2E:
    def test_restore_reinstalls_then_applies_patch(self, tmp_path, monkeypatch, project):
        """--restore should restore the package to a clean state, then apply the patch."""
        module_path = project["module_path"]
        version = project["version"]
        target_env = project["target_env"]

        # Create a patch via the normal workflow
        ws = tmp_path / "ws"
        monkeypatch.setattr(tempfile, "mkdtemp", _make_mock_mkdtemp(ws))
        prepare_patch_workspace(module_path, PACKAGE, version, target_env)

        ws_sp = find_site_packages(ws / "venv")
        six_py = ws_sp / "six.py"
        original = six_py.read_text()
        six_py.write_text(original + "\n# restore-e2e-marker\n")

        commit_changes(PACKAGE, version, ws_sp, target_env)

        patch_file = project["dir"] / "patches" / f"{PACKAGE}+{version}.patch"
        assert patch_file.exists()

        # The patch is now applied in target_env. Apply again with --restore
        # should succeed (restore cleans the already-patched state).
        apply_patch(patch_file, target_env, restore=True)

        patched_content = (find_site_packages(target_env) / "six.py").read_text()
        assert "# restore-e2e-marker" in patched_content
