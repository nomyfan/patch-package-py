import argparse
import logging
import sys
from logging import getLogger
from pathlib import Path

from patch_package_py.core import (
    CLI_NAME,
    PATCH_INFO_FILE,
    Resolver,
    apply_patch,
    commit_changes,
    find_site_packages,
    prepare_patch_workspace,
)

logger = getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


def cmd_patch(args):
    package_name = args.package
    resolver = Resolver()

    env_path = (
        Path(args.env_path) if args.env_path is not None else Path.cwd() / ".venv"
    )

    package = resolver.resolve_in_venv(env_path, package_name)
    if not package:
        logger.error(
            "Error: No package found",
        )
        sys.exit(1)
    module_path, version = package
    prepare_patch_workspace(
        module_path, package_name, version, env_path, amend=args.amend
    )


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
    with open(Path(git_dir) / PATCH_INFO_FILE) as f:
        import json

        info = json.load(f)
    site_packages_dir = Path(info["site_packages_path"])
    target_env_path = Path(info["target_env_path"])
    commit_changes(
        info["package_name"],
        info["version"],
        site_packages_dir,
        target_env_path,
        restore_target_package=not args.skip_restore,
    )
    import shutil

    shutil.rmtree(info["temp_dir"])


def cmd_apply(args):
    patches_dir = Path.cwd() / "patches"

    env_path = (
        Path(args.env_path) if args.env_path is not None else Path.cwd() / ".venv"
    )
    site_packages_dir = find_site_packages(env_path)

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
        apply_patch(
            patch_file,
            site_packages_dir,
            env_path=env_path if args.restore else None,
            restore=args.restore,
        )


def cli():
    from importlib.metadata import version

    parser = argparse.ArgumentParser(
        prog=CLI_NAME, description="A Python package patching tool"
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"patch-package-py {version('patch-package-py')}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # patch command
    workspace_parser = subparsers.add_parser(
        "patch", help="Prepare for patching a package"
    )
    workspace_parser.add_argument("package", help="Package name")
    workspace_parser.add_argument("-e", "--env-path", help="Environment Path")
    workspace_parser.add_argument(
        "--amend",
        action="store_true",
        help="Apply existing patch file to the workspace so you can continue editing",
    )
    workspace_parser.set_defaults(func=cmd_patch)

    # commit command
    commit_parser = subparsers.add_parser(
        "commit", help="Commit changes and create a patch file"
    )
    commit_parser.add_argument("path", help="Edit patch given by `patch` command")
    commit_parser.add_argument(
        "--skip-restore",
        action="store_true",
        help="Skip reinstalling the target package before applying the new patch",
    )
    commit_parser.set_defaults(func=cmd_commit)

    # apply command
    apply_parser = subparsers.add_parser("apply", help="Apply patches")
    apply_parser.add_argument("-e", "--env-path", help="Environment Path")
    apply_parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore the clean package before applying each patch",
    )
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
