from pathlib import Path, PurePosixPath
import tempfile
import os
import subprocess
import sys
from logging import getLogger
import posixpath

logger = getLogger(__name__)

CLI_NAME = "p12y"
PATCH_INFO_FILE = ".patch_info.json"


def find_site_packages(venv: Path) -> Path:
    # For Windows
    if os.name == "nt":
        return venv / "Lib" / "site-packages"

    # For Unix-like systems
    lib_path = venv / "lib"
    if lib_path.exists():
        python_dirs = list(lib_path.glob("python*"))
        if python_dirs:
            return python_dirs[0] / "site-packages"

    raise FileNotFoundError("Could not determine site-packages directory.")


class Resolver:
    def resolve_in_venv(
        self, venv: Path, package_name: str
    ) -> tuple[PurePosixPath, str] | None:
        site_packages_path = find_site_packages(venv)
        return self.resolve_in_site_packages(site_packages_path, package_name)

    def resolve_in_site_packages(
        self, site_packages_path: Path, package_name: str
    ) -> tuple[PurePosixPath, str] | None:
        dist_info = list(
            site_packages_path.glob(f"{package_name.replace('-', '_')}-*.dist-info")
        )
        if not dist_info:
            return None
        if len(dist_info) != 1:
            raise ValueError("unreachable")
        dist_info_path = dist_info[0]
        _, version = dist_info_path.stem.rsplit("-", 1)
        files = self._parse_record_file(dist_info_path)
        commonpath = self._find_commonpath(files)
        return commonpath, version

    def _parse_record_file(self, dist_info_path: Path) -> list[PurePosixPath]:
        record_file = dist_info_path / "RECORD"
        if not record_file.exists():
            return []

        files: list[PurePosixPath] = []
        with record_file.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Parse CSV-like format: path,hash,size
                parts = line.split(",")
                if len(parts) >= 1:
                    file_path = parts[0]
                    # Skip .dist-info files and external files
                    if (
                        ".dist-info/" not in file_path
                        and not file_path.startswith("./")
                        and not file_path.startswith("../")
                    ):
                        files.append(PurePosixPath(file_path))

        return files

    def _find_commonpath(self, files: list[PurePosixPath]) -> PurePosixPath:
        if not files:
            return PurePosixPath("")

        if len(files) == 1:
            # For single file, return its directory
            return files[0].parent

        common_path_str = posixpath.commonpath([str(p) for p in files])
        return PurePosixPath(common_path_str)


def prepare_patch_workspace(
    module_path: PurePosixPath, package_name: str, version: str
):
    temp_dir = Path(tempfile.mkdtemp(prefix=f"patch-{package_name}-{version}-"))
    venv_path = temp_dir / "venv"

    # Create venv with uv using current Python version
    subprocess.check_call(["uv", "venv", str(venv_path), "--python", sys.executable])

    # Install the package without dependencies using uv
    subprocess.check_call(
        [
            "uv",
            "pip",
            "install",
            "--no-deps",
            f"{package_name}=={version}",
            "--python",
            str(
                venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            ),
        ],
        cwd=temp_dir,
    )

    # Remove all directories ending with .dist-info
    site_packages_path = find_site_packages(venv_path)
    for dist_info in site_packages_path.glob("*.dist-info"):
        if dist_info.is_dir():
            import shutil

            shutil.rmtree(dist_info)
    # Remove _virtualenv.py and _virtualenv.pth if exist
    for extra_file in ["_virtualenv.py", "_virtualenv.pth"]:
        extra_path = site_packages_path / extra_file
        if extra_path.exists():
            extra_path.unlink()

    git_path = site_packages_path.parent
    edit_path = site_packages_path / module_path

    with open(git_path / ".gitignore", "w") as f:
        f.write(
            "__pycache__/\n*.py[oc]\nbuild/\ndist/\nwheels/\n*.egg-info\n_virtualenv.py\n_virtualenv.pth"
        )
    with open(git_path / PATCH_INFO_FILE, "w") as f:
        import json

        json.dump(
            {
                "temp_dir": str(temp_dir.absolute()),
                "venv_path": str(venv_path.absolute()),
                "site_packages_path": str(site_packages_path.absolute()),
                "package_name": package_name,
                "version": version,
            },
            f,
            indent=2,
        )
    subprocess.check_call(
        ["git", "init"],
        cwd=git_path,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    subprocess.check_call(
        ["git", "add", "."],
        cwd=git_path,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    subprocess.check_call(
        [
            "git",
            "commit",
            "--no-gpg-sign",
            "-m",
            f"Initial commit of {package_name}=={version}",
        ],
        cwd=git_path,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )

    logger.info(
        f"You can now edit the package in: {edit_path}. When done, run `{CLI_NAME} commit {edit_path}` in this directory to create the patch file."
    )


def commit_changes(package_name: str, version: str, site_packages_path: Path) -> None:
    diff_content = subprocess.check_output(
        ["git", "diff", "--relative"],
        cwd=site_packages_path,
        text=True,
    )

    if not diff_content:
        logger.info("No changes detected, nothing to commit.")
        return
    patch_file_name = f"{package_name}+{version}.patch"
    patches_dir = Path.cwd() / "patches"
    patches_dir.mkdir(exist_ok=True, parents=True)
    patch_file_path = patches_dir / patch_file_name
    with open(patch_file_path, "w") as f:
        f.write(diff_content)

    current_site_packages = find_site_packages(Path.cwd() / ".venv")
    try:
        apply_patch(patch_file_path, current_site_packages)
    except subprocess.CalledProcessError:
        logger.error(
            f"Error: failed to apply the patch after creation. There's maybe a conflict, you can try to reinstall the package and apply the patch manually via `{CLI_NAME} apply {patch_file_name}`"
        )
        return
    logger.info(f"Patch created and applied for {package_name}=={version}")


def apply_patch(patch_file: Path, site_packages_dir: Path) -> None:
    # Parse package name and version from patch file name
    patch_name = patch_file.stem  # Remove .patch extension
    if "+" not in patch_name:
        raise ValueError(
            f"Invalid patch file name format: {patch_file.name}. Expected format: package_name+version.patch"
        )

    package_name, version = patch_name.rsplit("+", 1)

    # Verify the package exists in site_packages_dir with matching version
    resolver = Resolver()
    result = resolver.resolve_in_site_packages(site_packages_dir, package_name)
    if result is None:
        logger.warning(
            f"Package '{package_name}' not found in site-packages directory, skipping..."
        )
        return

    _, installed_version = result
    if installed_version != version:
        raise ValueError(
            f"Version mismatch: patch is for {package_name}=={version} but installed version is {installed_version}"
        )

    # First, check if the patch is already applied using dry-run
    try:
        subprocess.check_call(
            [
                "patch",
                "-p1",
                "-N",
                "--dry-run",
                "--forward",
                "-i",
                str(patch_file.absolute()),
            ],
            cwd=site_packages_dir,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        logger.warning(
            f"Patch `{patch_name}` appears to be already applied, skipping...",
        )
        return

    # If dry-run succeeds, apply the patch for real
    subprocess.check_call(
        [
            "patch",
            "-p1",
            "-N",
            "--forward",
            "-i",
            str(patch_file.absolute()),
        ],
        cwd=site_packages_dir,
    )
