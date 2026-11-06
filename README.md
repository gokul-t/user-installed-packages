# user-installed-packages

List the packages **you** explicitly installed on this system — as opposed to
the OS image, its dependencies, and automatic updates.

Package managers on their own cannot answer this reliably:

- `dnf repoquery --userinstalled` includes every group package that was part
  of the image build (e.g. kiwi-built Fedora Workstation images mark **all**
  image packages as user-requested).
- `apt-mark showmanual` includes the base-OS packages recorded by the
  installer as manual.
- Kernels installed by system updates are versioned, reason-`User` packages.

`user-installed-packages` detects the packages the user asked for, excluding
the image base, and prints them. Its `report` subcommand compares installed
packages against a supplied manifest directory. Both are read-only: they
never install, remove, or edit anything.

## Installation

### Prebuilt binary

Install with [`bin`](https://github.com/marcosnils/bin), the binary package
manager:

```sh
bin install github.com/gokul-t/user-installed-packages
```

`bin` downloads the latest release binary for your platform (Linux amd64/arm64),
installs it into your user bin directory, and keeps it updated.

### pipx

```sh
pipx install git+https://github.com/gokul-t/user-installed-packages.git@v0.6.2
```

Any Python ≥ 3.10 works; there are no third-party dependencies.

## Usage

```sh
user-installed-packages                 # one package name per line
user-installed-packages --distro apt    # force the backend (auto-detected by default)
user-installed-packages --json          # full detection result as JSON
user-installed-packages --version
user-installed-packages report
```

Exit status: `0` on success, `2` on error (unsupported distro, missing
tools, backend failure). Warnings are printed to stderr and do not affect
the exit status.

### Package manifest report

The `report` subcommand compares Homebrew formulae, casks, taps, and VS Code
extensions on macOS; DNF and Flatpak on Fedora; and APT and Snap on Ubuntu.
By default, the report looks in `./ansible/packages` for `Brewfile`,
`dnf-packages.txt`, `apt-packages.txt`, `flatpak-packages.txt`, and
`snap-packages.txt`. Set `--manifest-dir` to change the directory, or
override any manifest independently. Relative manifest paths are resolved
under `--manifest-dir`; absolute paths are used as given.

```sh
user-installed-packages report --manifest-dir ./ansible/packages
user-installed-packages report --manifest-dir ./ansible/packages \
  --skip PACKAGE --no-flatpak --output ~/.local/state/dotfiles/package-report.txt
user-installed-packages report --manifest-dir ./personal/ansible/packages \
  --apt-manifest apt-packages.txt --snap-manifest snap-packages.txt
```

Available manifest options are `--brewfile`, `--dnf-manifest`,
`--apt-manifest`, `--flatpak-manifest`, and `--snap-manifest`. Repeat an option
to compare multiple manifests of the same type (for example shared and private
package lists). With no override, the conventional filenames above are used,
so existing invocations continue to work.

The report is read-only. `+` entries are installed but undeclared; `-`
entries are declared but not installed. Use `--skip NAME` repeatedly to
ignore packages. `--no-flatpak` and `--no-snap` disable those collectors.
Output files are written privately and serialized with a lock. Exit status is
`0` when all enabled collectors succeeded and `2` when one or more sources
could not be compared.

### JSON output

```json
{
  "backend": "dnf",
  "packages": ["fedy", "vim-enhanced"],
  "image_packages": ["glibc", "filesystem"],
  "excluded_auto": ["kernel", "kernel-core"],
  "warnings": []
}
```

- `packages` — what you asked for (the answer to the question).
- `image_packages` — detected OS image base packages (informational).
- `excluded_auto` — automatic versioned updates excluded (kernels on dnf).
- `warnings` — degradations (e.g. no installer log on apt; dnf history
  unavailable and an install-time fallback was used).

### Library use

```python
from user_installed_packages import detect

result = detect()                 # auto-detect the distro
result = detect("dnf")            # or force a backend
print(result.packages)
```

### Scheduling reports

Use `schedule_report()` to schedule automatic drift reports:

```python
from user_installed_packages import schedule_report

# Enable scheduled weekly reports (default)
schedule_report(command=["user-installed-packages", "report"])

# Disable the scheduler
schedule_report(enabled=False)
```

The `schedule` CLI subcommand provides a convenient interface:

```sh
# Enable scheduled reports
user-installed-packages schedule --enable --manifest-dir ./ansible/packages

# Disable the scheduler
user-installed-packages schedule --disable
```

The library automatically detects the best available scheduler:
- **Linux**: systemd user timer (default), cron (fallback)
- **macOS**: LaunchAgent

## How it works

### Fedora / RHEL-likes (dnf backend)

1. `dnf history list` is parsed for transactions; the base image is the set
   of packages installed in the initial transactions (e.g. the image build).
   If history is unavailable, the install-time window is used as a fallback
   and a warning is emitted.
2. `dnf repoquery --installed --qf '%{name} %{reason}'` selects packages
   whose reason is `User` (requested at the command line or via Software).
3. The base image set and automatically installed kernel packages are
   subtracted from the result.

### Debian / Ubuntu (apt backend)

1. `dpkg-query -W '${db:Status-Abbrev} ${Package}'` selects fully installed
   (`ii`) packages, stripping any `:arch` qualifier.
2. `apt-mark showmanual` selects manually installed packages.
3. The installer-recorded base set from `/var/log/installer/initial-status.gz`
   (or `initial-status`) is subtracted. If no installer log is found (e.g.
   container images) the base cannot be excluded; a warning is emitted and
   all manually installed packages are reported.

## Known limitations

- On image-built systems, group packages installed by the image are
  indistinguishable from packages the user explicitly requested. The dnf
  backend therefore compares only `reason=User` installs and only against
  the initial transactions; image-installed groups that report reason `User`
  are correctly treated as image packages, but a group *the user ran*
  themselves in the very first transactions would be misclassified.
- Dependency, weak-dependency and group installs are never reported.
- The dnf backend relies on `dnf history`; if it is purged or unreadable,
  the fallback install-time window may misclassify upgraded image packages
  as user-installed (a warning is emitted in that case).
- Package detection supports `dnf` (Fedora ≥ 41 / dnf5 and legacy dnf4) and
  `apt` (Debian, Ubuntu); the report also supports Homebrew, Flatpak, and Snap.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

CI runs the unit tests on supported Python versions and a smoke test inside
the `fedora:40` (dnf4), `fedora:44` (dnf5), `ubuntu:24.04` and `debian:13`
containers.

### Building a binary

```sh
python3 -m venv .venv
.venv/bin/pip install pyinstaller .
.venv/bin/pyinstaller --onefile --name user-installed-packages src/user_installed_packages/__main__.py
```

This produces `dist/user-installed-packages`. Release tarballs follow the
naming `user-installed-packages-v<version>.<os>-<arch>.tar.gz` and are
published as GitHub releases (which `bin` installs from) by the
[Release workflow](.github/workflows/release.yml) whenever a `v*` tag is pushed.

Releases are triggered by pushing a `v*` tag; the workflow builds the binary for
Linux (amd64/arm64), smoke tests it, and publishes the tarballs plus a
`checksums.txt` to the GitHub release.

## License

MIT — see [LICENSE](LICENSE).
