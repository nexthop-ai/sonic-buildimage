#!/bin/bash
# Installed on all PDDF based Nexthop platforms.
# Runs before PDDF.

# TODO: Move PDDF device JSON file programmatically to
#       /usr/share/sonic/device/${PLATFORM}/pddf/pddf-device.json
#       based on hardware API version.

log() {
  logger -t "pre_pddf_init" "$@"
}

nh_gen pddf_device_json
nh_gen pcie_yaml

if [ -e /sys/bus/i2c/devices/i2c-0 ]; then
  modprobe -r i2c_designware_platdrv 2>/dev/null || true
  modprobe -r i2c_designware_platform 2>/dev/null || true
  modprobe -r i2c_designware_core 2>/dev/null || true
  modprobe -r i2c_piix4 2>/dev/null || true
  modprobe -r i2c_asf 2>/dev/null || true
  cat << EOF > /etc/modprobe.d/blacklist-amd-i2c.conf
blacklist i2c_designware_platdrv
blacklist i2c_designware_platform
blacklist i2c_designware_core
blacklist i2c_piix4
blacklist i2c_asf
EOF
  update-initramfs -u
fi

ASIC_INIT_PATH="/usr/local/bin/asic_init.sh"
if [ -f "$ASIC_INIT_PATH" ]; then
  log "$ASIC_INIT_PATH found. Executing..."
  "$ASIC_INIT_PATH"
  RETURN_CODE=$?
  if [ $RETURN_CODE -ne 0 ]; then
    log -p error "$ASIC_INIT_PATH exited with error code: $RETURN_CODE"
  else
    log "$ASIC_INIT_PATH executed successfully."
  fi
else
  log -p warning "$ASIC_INIT_PATH not found."
fi

exit 0
