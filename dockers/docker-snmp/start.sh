#!/usr/bin/env bash


if [ "${RUNTIME_OWNER}" == "" ]; then
    RUNTIME_OWNER="kube"
fi

CTR_SCRIPT="/usr/share/sonic/scripts/container_startup.py"
if test -f ${CTR_SCRIPT}
then
    ${CTR_SCRIPT} -f snmp -o ${RUNTIME_OWNER} -v ${IMAGE_VERSION}
fi

mkdir -p /etc/ssw /etc/snmp

# Parse snmp.yml and insert the data in Config DB
/usr/bin/snmp_yml_to_configdb.py

SONIC_CFGGEN_ARGS=" \
    -d \
    -y /etc/sonic/sonic_version.yml \
    -t /usr/share/sonic/templates/sysDescription.j2,/etc/ssw/sysDescription \
    -t /usr/share/sonic/templates/snmpd.conf.j2,/etc/snmp/snmpd.conf \
"

sonic-cfggen $SONIC_CFGGEN_ARGS

mkdir -p /var/sonic
echo "# Config files managed by sonic-config-engine" > /var/sonic/config_status

# snmpd exits if an agentAddress IP is not assigned yet (e.g. Loopback0 during
# swss restart, issue #16486). Wait up to 60s for them; on timeout start anyway.
agent_addr_assigned() {
    ip -o addr show to "$1" 2>/dev/null | grep -q .
}

deadline=$((SECONDS + 60))
for addr in $(sed -n 's/^agentAddress[[:space:]]*[a-z6]*:\[\([^]%]*\).*/\1/p' /etc/snmp/snmpd.conf); do
    agent_addr_assigned "$addr" && continue
    started=$SECONDS
    until agent_addr_assigned "$addr" || [ $SECONDS -ge $deadline ]; do
        sleep 1
    done
    if agent_addr_assigned "$addr"; then
        logger -t snmp-start "agent address $addr assigned after $((SECONDS - started))s"
    else
        logger -t snmp-start "timed out waiting for agent address $addr, starting snmpd anyway"
    fi
done
