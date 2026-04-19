---
name: ec-su-axb35-kernel-module
description: Build, sign, install, and manage the ec_su_axb35 kernel module (Sixunited AXB35-02 Embedded Controller) for fan and power control on the m5 headless server.
version: 1.0
---

# ec_su_axb35 Kernel Module

Custom out-of-tree kernel module for the Sixunited AXB35-02 Embedded Controller. Provides fan control and APU power mode management on the m5 server (headless, BIOS power mode set to normal to avoid breaker trips on shared 16A circuit).

## Source Location

```
~/sources/ec-su_axb35-linux/
```

Contains: source (`src/`), Makefile, MOK signing keys (`MOK.key`, `MOK.der`), scripts (`scripts/su_axb35_monitor`).

## Sysfs Interface

Once loaded, the module exposes:
- `/sys/class/ec_su_axb35/apu/power_mode` — write `quiet`, `normal`, or `performance`
- Current setting: `echo quiet|normal|performance | sudo tee /sys/class/ec_su_axb35/apu/power_mode`

## Build for a Specific Kernel

The `.ko` is kernel-version specific (vermagic check). Must rebuild when kernel changes.

```bash
cd ~/sources/ec-su_axb35-linux
make clean
make KERNEL_BUILD=/lib/modules/TARGET_KERNEL/build
```

## Sign the Module (Secure Boot)

The server uses Secure Boot. The module must be signed with the MOK keys stored in the source dir:

```bash
cd ~/sources/ec-su_axb35-linux
kmodsign sha512 MOK.key MOK.der ec_su_axb35.ko
```

If MOK key is not yet enrolled on this kernel:
```bash
sudo mokutil --import MOK.der
# Enter a one-time password, then reboot
# At MOK Manager prompt: Enroll MOK → Continue → Enter password → Reboot
```

**Headless caveat:** MOK enrollment requires physical console or IPMI/serial to interact with Shim's MOK Manager at boot. Plan accordingly.

## Install

```bash
cd ~/sources/ec-su_axb35-linux
sudo make KERNEL_BUILD=/lib/modules/TARGET_KERNEL/build install
# This runs modules_install + depmod
```

Verify:
```bash
modinfo -n ec_su_axb35
sudo modprobe ec_su_axb35
lsmod | grep ec_su
ls /sys/class/ec_su_axb35/
```

## Set GRUB to Boot a Specific Kernel

When the module isn't built for the latest kernel yet, pin GRUB to the kernel that has it:

```bash
# Check available entries
sudo grep -E 'menuentry' /boot/grub/grub.cfg | grep -v 'recovery' | head -10

# Pin to specific kernel (e.g., 7.0.0-12)
sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 7.0.0-12-generic"/' /etc/default/grub
sudo update-grub
```

Revert to latest:
```bash
sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT=0/' /etc/default/grub
sudo update-grub
```

## Full Rebuild Workflow (new kernel)

```bash
cd ~/sources/ec-su_axb35-linux
make clean
make KERNEL_BUILD=/lib/modules/NEW_KERNEL/build
kmodsign sha512 MOK.key MOK.der ec_su_axb35.ko
sudo make KERNEL_BUILD=/lib/modules/NEW_KERNEL/build install

# If MOK already enrolled for this key, just reboot:
sudo reboot

# Pin GRUB to new kernel if needed
sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT=0/' /etc/default/grub
sudo update-grub
```

## Pitfalls

## Monitoring and automatic mode switching

You can add a lightweight watchdog that checks the APU power mode and temperature every 30 seconds. If the mode stays in `quiet` for longer than 10 minutes **and** the CPU temperature exceeds 65 °C, the watchdog will automatically switch the mode to `balanced` to avoid prolonged throttling.

### Example systemd service

Create `/etc/systemd/system/ec-apu-watchdog.service`:

```ini
[Unit]
Description=Watchdog for ec_su_axb35 APU power mode
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/ec-apu-watchdog.sh
```

Create the script `/usr/local/bin/ec-apu-watchdog.sh`:

```bash
#!/usr/bin/env bash
MODE=$(cat /sys/class/ec_su_axb35/apu/power_mode)
TEMP=$(cat /sys/class/thermal/thermal_zone*/temp | head -1)
# temperature in millidegree Celsius
if [[ "$MODE" == "quiet" && $TEMP -gt 65000 ]]; then
    echo "APU quiet mode + high temp, switching to balanced"
    echo balanced > /sys/class/ec_su_axb35/apu/power_mode
fi
```

Make it executable:

```bash
chmod +x /usr/local/bin/ec-apu-watchdog.sh
systemctl daemon-reload
systemctl enable --now ec-apu-watchdog.service
```

This ensures the system automatically falls back to a safer power mode without manual intervention.

## Monitoring and automatic mode switching

You can add a lightweight watchdog that checks the APU power mode and temperature every 30 seconds. If the mode stays in `quiet` for longer than 10 minutes **and** the CPU temperature exceeds 65°C, the watchdog will automatically switch the mode to `normal` to avoid prolonged throttling.

### Example systemd service

Create `/etc/systemd/system/ec-apu-watchdog.service`:

```ini
[Unit]
Description=Watchdog for ec_su_axb35 APU power mode
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/ec-apu-watchdog.sh
```

Create the script `/usr/local/bin/ec-apu-watchdog.sh`:

```bash
#!/usr/bin/env bash
MODE=$(cat /sys/class/ec_su_axb35/apu/power_mode)
TEMP=$(cat /sys/class/thermal/thermal_zone*/temp | head -1)
# temperature in millidegree Celsius
if [[ "$MODE" == "quiet" && $TEMP -gt 65000 ]]; then
    echo "APU quiet mode + high temp, switching to normal"
    echo normal > /sys/class/ec_su_axb35/apu/power_mode
fi
```

Make it executable:

```bash
chmod +x /usr/local/bin/ec-apu-watchdog.sh
systemctl daemon-reload
systemctl enable --now ec-apu-watchdog.service
```

This ensures the system automatically falls back to a safer power mode without manual intervention.

- **Version mismatch:** Module won't load if vermagic doesn't match running kernel. Always rebuild.
- **Secure Boot:** Unsigned module will be rejected. Always sign with MOK keys.
- **Unattended upgrades** may install a new kernel and remove old ones. After a kernel update, the module must be rebuilt or GRUB pinned to the old kernel.
- **DKMS not used** — this module is not registered with DKMS, so it won't auto-rebuild on kernel updates. Consider setting up DKMS if kernel changes become frequent.
- **Duplicate .ko files:** The module has been found in both `/lib/modules/KVER/updates/` and `/lib/modules/KVER/extra/`. The `updates/` path takes precedence. Clean up duplicates if needed.
- **Power mode caution:** APU power mode `performance` can trip the breaker on the shared 16A circuit. Use `normal` for the BIOS, `normal` or `quiet` for APU power mode.
