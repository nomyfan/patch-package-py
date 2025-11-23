import subprocess
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

from patch_package_py.core import (
    Resolver,
    apply_patch,
    commit_changes,
    find_site_packages,
)


class TestFindSitePackages:
    def test_unix_site_packages(self, tmp_path: Path):
        """Test finding site-packages on Unix-like systems."""
        # Create mock venv structure
        site_packages = tmp_path / "lib" / "python3.9" / "site-packages"
        site_packages.mkdir(parents=True)

        with patch("os.name", "posix"):
            result = find_site_packages(tmp_path)
            assert result == site_packages

    def test_windows_site_packages(self, tmp_path: Path):
        """Test finding site-packages on Windows."""
        site_packages = tmp_path / "Lib" / "site-packages"
        site_packages.mkdir(parents=True)

        with patch("os.name", "nt"):
            result = find_site_packages(tmp_path)
            assert result == site_packages

    def test_no_site_packages_raises(self, tmp_path: Path):
        """Test that missing site-packages raises FileNotFoundError."""
        with patch("os.name", "posix"), pytest.raises(FileNotFoundError):
            find_site_packages(tmp_path)


class TestResolver:
    def test_parse_record_file(self, tmp_path: Path):
        """Test parsing RECORD file from dist-info."""
        dist_info = tmp_path / "mypackage-1.0.0.dist-info"
        dist_info.mkdir()
        record = dist_info / "RECORD"
        record.write_text(
            "mypackage/__init__.py,sha256=abc,100\n"
            "mypackage/core.py,sha256=def,200\n"
            "mypackage-1.0.0.dist-info/METADATA,,\n"
            "../outside.py,,\n"
            "./relative.py,,\n"
        )

        resolver = Resolver()
        files = resolver._parse_record_file(dist_info)

        assert len(files) == 2
        assert PurePosixPath("mypackage/__init__.py") in files
        assert PurePosixPath("mypackage/core.py") in files

    def test_parse_record_file_empty(self, tmp_path: Path):
        """Test parsing empty or missing RECORD file."""
        dist_info = tmp_path / "mypackage-1.0.0.dist-info"
        dist_info.mkdir()

        resolver = Resolver()
        files = resolver._parse_record_file(dist_info)
        assert files == []

    def test_find_commonpath_multiple_files(self):
        """Test finding common path for multiple files."""
        resolver = Resolver()
        files = [
            PurePosixPath("mypackage/__init__.py"),
            PurePosixPath("mypackage/core.py"),
            PurePosixPath("mypackage/utils/helpers.py"),
        ]
        result = resolver._find_commonpath(files)
        assert result == PurePosixPath("mypackage")

    def test_find_commonpath_single_file(self):
        """Test finding common path for single file."""
        resolver = Resolver()
        files = [PurePosixPath("mypackage/core.py")]
        result = resolver._find_commonpath(files)
        assert result == PurePosixPath("mypackage")

    def test_find_commonpath_empty(self):
        """Test finding common path for empty list."""
        resolver = Resolver()
        result = resolver._find_commonpath([])
        assert result == PurePosixPath("")

    def test_resolve_in_site_packages(self, tmp_path: Path):
        """Test resolving package in site-packages."""
        # Create mock dist-info
        dist_info = tmp_path / "my_package-2.0.0.dist-info"
        dist_info.mkdir()
        record = dist_info / "RECORD"
        record.write_text(
            "my_package/__init__.py,sha256=abc,100\n"
            "my_package/module.py,sha256=def,200\n"
        )

        resolver = Resolver()
        result = resolver.resolve_in_site_packages(tmp_path, "my-package")

        assert result is not None
        module_path, version = result
        assert module_path == PurePosixPath("my_package")
        assert version == "2.0.0"

    def test_resolve_in_site_packages_not_found(self, tmp_path: Path):
        """Test resolving non-existent package."""
        resolver = Resolver()
        result = resolver.resolve_in_site_packages(tmp_path, "nonexistent")
        assert result is None


class TestApplyPatch:
    """Integration tests for the apply_patch workflow."""

    def _setup_site_packages(self, tmp_path: Path, package_name: str, version: str):
        """Helper to create a mock site-packages with a package installed."""
        site_packages = tmp_path / "site-packages"
        site_packages.mkdir()

        # Create dist-info
        dist_info = (
            site_packages / f"{package_name.replace('-', '_')}-{version}.dist-info"
        )
        dist_info.mkdir()
        (dist_info / "RECORD").write_text(
            f"{package_name}/__init__.py,sha256=abc123,50\n"
            f"{package_name}/core.py,sha256=def456,200\n"
        )

        # Create package files
        pkg_dir = site_packages / package_name
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('__version__ = "1.0.0"\n')
        (pkg_dir / "core.py").write_text("def hello():\n    return 'hello'\n")

        return site_packages

    def test_apply_patch_invalid_name_format(self, tmp_path: Path, caplog):
        """Test that invalid patch file name is skipped."""
        site_packages = self._setup_site_packages(tmp_path, "mypackage", "1.0.0")
        patch_file = tmp_path / "invalid_name.patch"
        patch_file.write_text("some patch content")

        apply_patch(patch_file, site_packages)

        assert "Invalid patch file name format" in caplog.text

    def test_apply_patch_package_not_found(self, tmp_path: Path, caplog):
        """Test that missing package is skipped."""
        site_packages = self._setup_site_packages(tmp_path, "mypackage", "1.0.0")
        patch_file = tmp_path / "otherpackage+1.0.0.patch"
        patch_file.write_text("some patch content")

        apply_patch(patch_file, site_packages)

        assert "not found in site-packages" in caplog.text

    def test_apply_patch_version_mismatch(self, tmp_path: Path):
        """Test that version mismatch raises error."""
        site_packages = self._setup_site_packages(tmp_path, "mypackage", "1.0.0")
        patch_file = tmp_path / "mypackage+2.0.0.patch"
        patch_file.write_text("some patch content")

        with pytest.raises(ValueError, match="Version mismatch"):
            apply_patch(patch_file, site_packages)

    def test_apply_patch_success(self, tmp_path: Path):
        """Test successful patch application."""
        site_packages = self._setup_site_packages(tmp_path, "mypackage", "1.0.0")
        patch_file = tmp_path / "mypackage+1.0.0.patch"
        patch_file.write_text(
            "--- a/mypackage/core.py\n"
            "+++ b/mypackage/core.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def hello():\n"
            "-    return 'hello'\n"
            "+    return 'hello world'\n"
        )

        with patch("subprocess.check_call") as mock_check_call:
            apply_patch(patch_file, site_packages)

            # Should be called twice: dry-run and actual apply
            assert mock_check_call.call_count == 2

    def test_apply_patch_already_applied(self, tmp_path: Path, caplog):
        """Test that already applied patch is skipped."""
        site_packages = self._setup_site_packages(tmp_path, "mypackage", "1.0.0")
        patch_file = tmp_path / "mypackage+1.0.0.patch"
        patch_file.write_text("some patch content")

        with patch("subprocess.check_call") as mock_check_call:
            # Simulate dry-run failure (patch already applied)
            mock_check_call.side_effect = subprocess.CalledProcessError(1, "patch")

            apply_patch(patch_file, site_packages)

            assert "already applied" in caplog.text


class TestCommitChanges:
    """Tests for creating patch files via commit_changes."""

    def test_commit_no_changes(self, tmp_path: Path, caplog, monkeypatch):
        """Test that no patch is created when there are no changes."""
        import logging

        caplog.set_level(logging.INFO)
        monkeypatch.chdir(tmp_path)

        with patch("subprocess.check_output", return_value=""):
            commit_changes("mypackage", "1.0.0", tmp_path)

        assert "No changes detected" in caplog.text
        assert not (tmp_path / "patches").exists()

    def test_commit_creates_patch_file(self, tmp_path: Path, monkeypatch):
        """Test that patch file is created with correct name and content."""
        monkeypatch.chdir(tmp_path)

        # Create .venv structure for find_site_packages
        site_packages = tmp_path / ".venv" / "lib" / "python3.9" / "site-packages"
        site_packages.mkdir(parents=True)
        dist_info = site_packages / "mypackage-1.0.0.dist-info"
        dist_info.mkdir()
        (dist_info / "RECORD").write_text("mypackage/__init__.py,,\n")

        diff_content = (
            "--- a/mypackage/core.py\n"
            "+++ b/mypackage/core.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )

        with (
            patch("subprocess.check_output", return_value=diff_content),
            patch("subprocess.check_call"),  # mock patch command
        ):
            commit_changes("mypackage", "1.0.0", tmp_path)

        patch_file = tmp_path / "patches" / "mypackage+1.0.0.patch"
        assert patch_file.exists()
        assert patch_file.read_text() == diff_content

    def test_commit_patch_file_naming(self, tmp_path: Path, monkeypatch):
        """Test patch file naming with package name and version."""
        monkeypatch.chdir(tmp_path)

        site_packages = tmp_path / ".venv" / "lib" / "python3.9" / "site-packages"
        site_packages.mkdir(parents=True)
        dist_info = site_packages / "my_package-2.5.0.dist-info"
        dist_info.mkdir()
        (dist_info / "RECORD").write_text("my_package/__init__.py,,\n")

        with (
            patch("subprocess.check_output", return_value="some diff"),
            patch("subprocess.check_call"),
        ):
            commit_changes("my-package", "2.5.0", tmp_path)

        assert (tmp_path / "patches" / "my-package+2.5.0.patch").exists()
