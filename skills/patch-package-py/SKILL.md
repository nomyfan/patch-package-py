---
name: patch-package-py
description: Use this skill whenever the user wants to use the `patch-package-py` or `p12y` CLI to patch an installed third-party Python package, create a patch file, apply patches from a `patches/` directory, choose an environment path with `-e`, or troubleshoot normal CLI outcomes.
license: MIT
compatibility: Requires Python >= 3.9, uv, git, and the patch utility. Windows users can install patch with Chocolatey, winget, or Cygwin.
---

# Patch Package Py CLI

## What `p12y` does

`patch-package-py` provides the `p12y` command for editing installed third-party Python packages and saving those edits as reusable patch files.

The CLI has three commands:

```bash
p12y patch <package> [-e <env-path>] [--amend]
p12y commit <edit-path> [--skip-restore]
p12y apply [-e <env-path>]
```

## CLI availability and uv-based workflow

`patch-package-py` is currently designed around uv-managed project environments. Use uv examples in this skill because uv is the primary workflow for installing the CLI, running commands, creating the temporary patch workspace, and applying patches.

From the uv project root that will own the patch files, verify the command first:

```bash
uv run p12y --help
```

When the command is available, continue with the patch workflow. When uv reports that `p12y` or `patch-package-py` is unavailable, install it into the project and verify again:

```bash
uv add patch-package-py
uv run p12y --help
```

For projects managed by a different package manager, treat the workflow as project-specific adaptation: identify how that tool exposes console scripts, find the virtual environment path, then adjust the command invocation and `-e <env-path>` values to match the actual project setup.

uv is required on the machine where `p12y patch` runs. The patch workspace setup uses uv to create the temporary virtual environment and install the exact package version into it.

## Invocation style

`p12y` is installed as a script inside a Python environment. Choose one invocation style and use it consistently from the project root.

Default examples use uv: `uv run p12y ...`. For projects managed by a different package manager, adapt this invocation to the actual project command runner and environment path.

The default environment path is `./.venv`. Use `-e` or `--env-path` when the virtual environment lives elsewhere.

Patch files are stored in the current project's `patches/` directory:

```text
patches/<package-name>+<version>.patch
```

## Standard workflow

Use this sequence when guiding a user through patching a package:

1. Go to the project root that owns the virtual environment and will store the patch.
2. Verify that `p12y` is available:

   ```bash
   uv run p12y --help
   ```

   When uv reports that `p12y` or `patch-package-py` is unavailable, install and verify again:

   ```bash
   uv add patch-package-py
   uv run p12y --help
   ```

3. Prepare an editable copy of the installed package:

   ```bash
   uv run p12y patch <package>
   ```

   For a custom environment:

   ```bash
   uv run p12y patch <package> -e <env-path>
   ```

   To continue editing an existing patch rather than starting from a clean copy, add `--amend`:

   ```bash
   uv run p12y patch <package> --amend
   ```

   `--amend` applies the patch file from `patches/<package-name>+<version>.patch` (if it exists) onto the fresh workspace so your previous changes are already present when you open the editor. If the patch cannot be applied cleanly, `p12y` falls back to a clean workspace and logs a warning.

4. Edit files inside the path printed by `p12y patch`.
5. Commit the edited package copy from the project root:

   ```bash
   uv run p12y commit <edit-path>
   ```

   `commit` writes the patch file, reinstalls the original package in the
   environment selected during `patch`, then applies the new patch. Use
   `--skip-restore` when the target environment is already prepared for direct
   patch application.

6. Apply all patch files in `patches/` to the selected environment:

   ```bash
   uv run p12y apply
   ```

   For a custom environment:

   ```bash
   uv run p12y apply -e <env-path>
   ```

7. Run a small import verification check for the patched behavior.

## Custom environment paths

Pass a virtual environment path to `p12y patch` and `p12y apply` with `-e`:

```bash
uv run p12y patch <package> -e <env-path>
uv run p12y commit <edit-path>
uv run p12y apply -e <env-path>
```

Run `uv run p12y commit <edit-path>` from the project root so the patch file lands in that project's `patches/` directory.

`p12y commit` writes `patches/<package-name>+<version>.patch`, restores the package in the environment recorded by `p12y patch`, and applies the new patch there. With `p12y patch <package> -e <env-path>`, `commit` reuses that same environment path.

## Troubleshooting

- `Error: No package found`: install the package in the selected environment, or pass the environment path with `-e <env-path>`.
- `Could not determine site-packages directory`: pass a virtual environment path that contains `Lib/site-packages` on Windows or `lib/python*/site-packages` on Unix-like systems.
- `Version mismatch`: recreate the patch for the installed version, or install the package version named in the patch file.
- `Invalid patch file name format`: use `patches/<package-name>+<version>.patch`.
- `appears to be already applied`: the selected environment already contains the patch changes.
- `No changes detected`: edit files inside the path printed by `uv run p12y patch`, then rerun `uv run p12y commit <edit-path>`.
