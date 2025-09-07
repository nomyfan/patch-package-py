# patch-package-py

A Python package patching tool that allows you to make and apply patches to third-party packages in your virtual environment.

## Installation

```bash
uv add patch-package-py
```

## Usage

The tool provides three main commands via the `p12y` CLI:

### 1. Create a patch workspace

```bash
p12y patch <package_name>
```

This command:

- Resolves the package from your current virtual environment (`.venv`)
- Creates a temporary virtual environment
- Installs the same version of the package without dependencies
- Sets up a git repository for tracking changes
- Provides a path where you can edit the package files

Example:

```bash
p12y patch requests
```

### 2. Commit changes and create patch file

```bash
p12y commit <edit_path>
```

After editing the package files, use this command to:

- Generate a git diff of your changes
- Create a `.patch` file in the `patches/` directory
- Test that the patch can be applied successfully

Example:

```bash
p12y commit /tmp/patch-requests-2.28.1-abc123/venv/lib/python3.11/site-packages/requests
```

### 3. Apply patches

```bash
p12y apply
```

This command:

- Looks for `.patch` files in the `patches/` directory
- Applies them to the packages in your current virtual environment (`.venv`)
- Reports success/failure for each patch

## Workflow

1. **Prepare for patching**: Run `p12y patch <package_name>` to set up a workspace
2. **Make your changes**: Edit the files in the provided path
3. **Create the patch**: Run `p12y commit <path>` to generate the patch file
4. **Apply patches**: Run `p12y apply` in your project to apply all patches

## How it works

- Uses `uv` for fast virtual environment creation and package installation
- Leverages git for tracking changes and generating diffs
- Stores patch files in a `patches/` directory in your project root
- Patch files are named using the format: `<package-name>+<version>.patch`

## Requirements

- Python ≥ 3.9
- `uv` package manager
- `git` version control system
- `patch` utility (typically pre-installed on Unix-like systems)

## License

MIT
