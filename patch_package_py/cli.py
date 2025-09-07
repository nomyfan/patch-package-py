import argparse
import sys
from pathlib import Path
from patch_package_py import (
    prepare_patch_workspace,
    commit_changes,
    apply_patch,
    Resolver,
    find_site_packages,
    PATCH_INFO_FILE,
    CLI_NAME,
)
from logging import getLogger
import logging

logger = getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


def cmd_patch(args):
    package_name = args.package
    resolver = Resolver()
    package = resolver.resolve_in_venv(Path.cwd() / ".venv", package_name)
    if not package:
        logger.error(
            "Error: No package found",
        )
        sys.exit(1)
    module_path, version = package
    prepare_patch_workspace(module_path, package_name, version)


def cmd_commit(args):
    edit_path = Path(args.path)
    if not edit_path.exists() or not edit_path.is_dir():
        logger.error(
            f"Error: Path {edit_path} does not exist or is not a directory",
        )
        sys.exit(1)
    import subprocess

    git_dir = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=edit_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    with open(Path(git_dir) / PATCH_INFO_FILE, "r") as f:
        import json

        info = json.load(f)
    site_packages_dir = Path(info["site_packages_path"])
    commit_changes(info["package_name"], info["version"], site_packages_dir)
    import shutil

    shutil.rmtree(info["temp_dir"])


def cmd_apply(args):
    patches_dir = Path.cwd() / "patches"
    site_packages_dir = find_site_packages(Path.cwd() / ".venv")

    if not patches_dir.exists():
        return

    if not site_packages_dir.exists():
        logger.error(
            f"Error: Site-packages directory {site_packages_dir} does not exist",
        )
        sys.exit(1)

    patch_files = list(patches_dir.glob("*.patch"))

    if not patch_files:
        logger.info(f"No patch files found in {patches_dir}")
        return

    for patch_file in patch_files:
        apply_patch(patch_file, site_packages_dir)


def cli():
    parser = argparse.ArgumentParser(
        prog=CLI_NAME, description="A Python package patching tool"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # patch command
    workspace_parser = subparsers.add_parser(
        "patch", help="Prepare for patching a package"
    )
    workspace_parser.add_argument("package", help="Package name")
    workspace_parser.set_defaults(func=cmd_patch)

    # commit command
    commit_parser = subparsers.add_parser(
        "commit", help="Commit changes and create a patch file"
    )
    commit_parser.add_argument("path", help="Edit patch given by `patch` command")
    commit_parser.set_defaults(func=cmd_commit)

    # apply command
    apply_parser = subparsers.add_parser("apply", help="Apply patches")
    apply_parser.set_defaults(func=cmd_apply)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
