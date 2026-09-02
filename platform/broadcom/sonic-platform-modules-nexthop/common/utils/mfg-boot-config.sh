#!/bin/bash
#
# MFG SONiC Configuration Script
#
# Run by the sonic-platform-nexthop-common postinst on first boot when mfg mode
# is requested (the /host/nexthop_mfg_mode marker dropped by the ONIE installer). It:
#   - Removes PDDF support file to prevent PDDF initialization
#   - Stops and disables syncd + pmon to prevent hardware acess via systemd services
#   - Creates /disable_asic file to prevent ASIC initialization sequence
#
# This allows manufacturing tests to have full control over hardware initialization
# and programming of firmware.
#

set -e

# Define constants and logging functions first
MACHINE_CONF="/host/machine.conf"
DEVICE_DIR="/usr/share/sonic/device"
DISABLE_ASIC_FILE="/disable_asic"
LOG_TAG="mfg-boot-config"
LOG_PRIO="user.info"
LOG_ERR="user.err"

log_info() {
    logger -t $LOG_TAG -p $LOG_PRIO "$1"
}

log_error() {
    logger -t $LOG_TAG -p $LOG_ERR "$1"
}

SYSTEMD_OVERRIDE_DIR="/etc/systemd/system"
MFG_MODE_MARKER="/etc/sonic/mfg_mode"
OVERRIDE_TEMPLATE="/tmp/mfg-mode-override.conf"

# Create MFG mode marker file
touch "${MFG_MODE_MARKER}"
log_info "Created MFG mode marker: ${MFG_MODE_MARKER}"

# Create the override file template once
cat > "${OVERRIDE_TEMPLATE}" << EOF
[Unit]
# MFG mode override - prevent service from starting
ConditionPathExists=!${MFG_MODE_MARKER}
EOF

# Function to create drop-in override for a service by copying the template
# and stops service so if restarted later in boot process the override will take
# effect
create_service_override() {
    local service_name="$1"
    local override_dir="${SYSTEMD_OVERRIDE_DIR}/${service_name}.d"
    local override_file="${override_dir}/mfg-mode-override.conf"

    mkdir -p "${override_dir}"

    cp "${OVERRIDE_TEMPLATE}" "${override_file}"

    log_info "Created override for ${service_name}: ${override_file}"

    # Stop the service if it exists (no-op if already stopped)
    if systemctl cat "${service_name}" >/dev/null 2>&1; then
        systemctl stop "${service_name}" 2>/dev/null
        log_info "Stopped ${service_name}"
    fi
}

# Disable asic-init sequence to prevent ASIC taking ASIC out of reset
if [ ! -f "${DISABLE_ASIC_FILE}" ]; then
    log_info "Creating ${DISABLE_ASIC_FILE}"
    touch "${DISABLE_ASIC_FILE}"
    if [ $? -eq 0 ]; then
        log_info "${DISABLE_ASIC_FILE} created successfully"
    else
        log_error "Failed to create ${DISABLE_ASIC_FILE}"
    fi
else
    log_info "${DISABLE_ASIC_FILE} already exists"
fi

# Remove PDDF support file to prevent PDDF initialization (drivers + devices)
# All the ONIE platform detection is just to locate this file
if [ -f "${MACHINE_CONF}" ]; then
    ONIE_PLATFORM=$(grep -E '^onie_platform=' "${MACHINE_CONF}" | cut -d= -f2 | tr -d '"' | tr -d "'" | sed 's/#.*//' | tr -d ' ')

    if [ -n "${ONIE_PLATFORM}" ]; then
        PLATFORM_DIR="${DEVICE_DIR}/${ONIE_PLATFORM}"
        log_info "Using platform directory: ${PLATFORM_DIR}"

        if [ -d "${PLATFORM_DIR}" ]; then
            PDDF_SUPPORT_FILE="${PLATFORM_DIR}/pddf_support"
            if [ -f "${PDDF_SUPPORT_FILE}" ]; then
                rm -f "${PDDF_SUPPORT_FILE}"
                log_info "Removed ${PDDF_SUPPORT_FILE}"
            fi
        fi
    fi
fi

# Create overrides for services that should not run in MFG mode
create_service_override "syncd.service"
create_service_override "pmon.service"
create_service_override "opennsl-modules.service"
create_service_override "port-ledd.service"
create_service_override "system-ledd.service"
create_service_override "transceiver-init.service"
create_service_override "rtc-sync.timer"

# Clean up the template file
rm -f "${OVERRIDE_TEMPLATE}"

exit 0
