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
the image base, and prints them. It is read-only: it never installs,
removes, or edits anything.

## Installation

```sh
pipx install git+https://github.com/gokul-t/user-installed-packages.git@v0.1.0
```

Any Python ≥ 3.10 works; there are no third-party dependencies.

## Usage

```sh
user-installed-packages                 # one package name per line
user-installed-packages --distro apt    # force the backend (auto-detected by default)
user-installed-packages --json          # full detection result as JSON
user-installed-packages --version
```

Exit status: `0` on success, `2` on error (unsupported distro, missing
tools, backend failure). Warnings are printed to stderr and do not affect
the exit status.

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
- Only `dnf` (Fedora ≥ 41 / dnf5 and legacy dnf4) and `apt` (Debian, Ubuntu)
  are supported today. Contributions welcome.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

CI runs the unit tests on supported Python versions and a smoke test inside
the `fedora:40` (dnf4), `fedora:44` (dnf5), `ubuntu:24.04` and `debian:13`
containers.

## License

MIT — see [LICENSE](LICENSE).
