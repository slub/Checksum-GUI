#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(dirname -- "$script_dir")"

for tool in python3 dpkg-deb; do
    command -v "$tool" >/dev/null || { echo "Required tool missing: $tool" >&2; exit 1; }
done

version="$(python3 "$script_dir/version.py")"
output_dir="${1:-$script_dir/dist}"
mkdir -p "$output_dir"
staging="$(mktemp -d)"
trap 'rm -rf -- "$staging"' EXIT
chmod 755 "$staging"

install -d "$staging/DEBIAN" "$staging/usr/share/chksmg" "$staging/usr/bin" "$staging/usr/share/applications"
for file in main.py checksums.py config.py notifications.py results.py taskbar.py translations.py icon.ico; do
    install -m 644 "$repo_dir/$file" "$staging/usr/share/chksmg/$file"
done

cat > "$staging/DEBIAN/control" <<CONTROL
Package: chksmg
Version: $version
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-pyqt6
Recommends: libnotify-bin
Maintainer: Georg Sieber <georg.sieber@slub-dresden.de>
Description: #pruefsummencool
CONTROL

cat > "$staging/usr/bin/chksmg" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 /usr/share/chksmg/main.py "$@"
LAUNCHER

chmod 755 "$staging/usr/bin/chksmg"
install -m 644 "$script_dir/chksmg.desktop" "$staging/usr/share/applications/chksmg.desktop"
dpkg-deb --root-owner-group --build "$staging" "$output_dir/chksmg.deb"
echo "Built $output_dir/chksmg.deb"
