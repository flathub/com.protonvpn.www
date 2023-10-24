# ProtonVPN

High-speed Swiss VPN that safeguards your privacy.

## How do I automatically connect to the VPN server I connected to last time?

Copy

- `/var/lib/flatpak/app/com.protonvpn.www/current/active/export/share/applications/com.protonvpn.www.desktop` if Proton VPN is installed to the system; or
- `~/.local/share/flatpak/app/com.protonvpn.www/current/active/export/share/applications/com.protonvpn.www.desktop` if Proton VPN is installed to the user

to `~/.config/autostart/`.
