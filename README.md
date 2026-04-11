# ProtonVPN

High-speed Swiss VPN that safeguards your privacy.

## How do I automatically connect to the VPN server I connected to last time?

Copy

- `/var/lib/flatpak/app/com.protonvpn.www/current/active/export/share/applications/com.protonvpn.www.desktop` if Proton VPN is installed to the system; or
- `~/.local/share/flatpak/app/com.protonvpn.www/current/active/export/share/applications/com.protonvpn.www.desktop` if Proton VPN is installed to the user

to `~/.config/autostart/`.

## Using the CLI

The Proton VPN CLI is available in this Flatpak build.

```bash
# Show help
flatpak run com.protonvpn.www protonvpn --help

# Show connection status
flatpak run com.protonvpn.www protonvpn status

# Sign in and connect
flatpak run com.protonvpn.www protonvpn signin
flatpak run com.protonvpn.www protonvpn connect

# Disconnect
flatpak run com.protonvpn.www protonvpn disconnect
```

For convenience, add an alias in your shell profile:

```bash
alias protonvpn='flatpak run com.protonvpn.www protonvpn'
```

## Updating CLI dependencies

When `proton-vpn-cli` updates runtime dependencies, regenerate the resources file with:

```bash
flatpak-pip-generator --checker-data --yaml --runtime='org.gnome.Sdk//49' click dbus-fast tabulate -o pip-resources.proton-vpn-cli
```
