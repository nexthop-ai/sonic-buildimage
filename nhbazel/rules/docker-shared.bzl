"""Shared docker fleet data: the dockers common to more than one platform image.

The docker analog of the shared package rules -- ONE place for the specs (deps/base/release)
and the label lists of the dockers that appear across platforms, imported + extended by the
per-platform modules (platform/<p>/<p>.bzl). Platform-specific dockers (syncd-brcm, dash-engine,
sonic-redfish, sonic-mgmt, ...) live in their platform module, not here. Holds DATA only -- the
derivation over it is in lib/prebuilt_tokens.bzl + lib/docker_membership.bzl.

Each docker's DEPS is single-sourced from its own docker-<stem>.bzl (the same constant its
docker_image() call uses), so SHARED_SPECS can't drift from what the dockers actually install.
"""

load(":nhbazel/rules/docker-base-trixie.bzl", BASE_TRIXIE_DEPS = "DEPS")
load(":nhbazel/rules/docker-bmp-watchdog.bzl", BMP_WATCHDOG_DEPS = "DEPS")
load(":nhbazel/rules/docker-bmp.bzl", SONIC_BMP_DEPS = "DEPS")
load(":nhbazel/rules/docker-config-engine-trixie.bzl", CONFIG_ENGINE_TRIXIE_DEPS = "DEPS")
load(":nhbazel/rules/docker-dash-ha.bzl", DASH_HA_DEPS = "DEPS")
load(":nhbazel/rules/docker-database.bzl", DATABASE_DEPS = "DEPS")
load(":nhbazel/rules/docker-dhcp-relay.bzl", DHCP_RELAY_DEPS = "DEPS")
load(":nhbazel/rules/docker-eventd.bzl", EVENTD_DEPS = "DEPS")
load(":nhbazel/rules/docker-fpm-frr.bzl", FPM_FRR_DEPS = "DEPS")
load(":nhbazel/rules/docker-gnmi-sidecar.bzl", GNMI_SIDECAR_DEPS = "DEPS")
load(":nhbazel/rules/docker-gnmi-watchdog.bzl", GNMI_WATCHDOG_DEPS = "DEPS")
load(":nhbazel/rules/docker-gnmi.bzl", SONIC_GNMI_DEPS = "DEPS")
load(":nhbazel/rules/docker-iccpd.bzl", ICCPD_DEPS = "DEPS")
load(":nhbazel/rules/docker-lldp.bzl", LLDP_DEPS = "DEPS")
load(":nhbazel/rules/docker-macsec.bzl", MACSEC_DEPS = "DEPS")
load(":nhbazel/rules/docker-mux.bzl", MUX_DEPS = "DEPS")
load(":nhbazel/rules/docker-nat.bzl", NAT_DEPS = "DEPS")
load(":nhbazel/rules/docker-orchagent.bzl", ORCHAGENT_DEPS = "DEPS")
load(":nhbazel/rules/docker-otel.bzl", SONIC_OTEL_DEPS = "DEPS")
load(":nhbazel/rules/docker-p4rt.bzl", SONIC_P4RT_DEPS = "DEPS")
load(":nhbazel/rules/docker-platform-monitor.bzl", PLATFORM_MONITOR_DEPS = "DEPS")
load(":nhbazel/rules/docker-restapi-sidecar.bzl", RESTAPI_SIDECAR_DEPS = "DEPS")
load(":nhbazel/rules/docker-restapi-watchdog.bzl", RESTAPI_WATCHDOG_DEPS = "DEPS")
load(":nhbazel/rules/docker-restapi.bzl", SONIC_RESTAPI_DEPS = "DEPS")
load(":nhbazel/rules/docker-router-advertiser.bzl", ROUTER_ADVERTISER_DEPS = "DEPS")
load(":nhbazel/rules/docker-sflow.bzl", SFLOW_DEPS = "DEPS")
load(":nhbazel/rules/docker-snmp.bzl", SNMP_DEPS = "DEPS")
load(":nhbazel/rules/docker-sonic-mgmt-framework.bzl", SONIC_MGMT_FRAMEWORK_DEPS = "DEPS")
load(":nhbazel/rules/docker-swss-layer-trixie.bzl", SWSS_LAYER_TRIXIE_DEPS = "DEPS")
load(":nhbazel/rules/docker-sysmgr.bzl", SYSMGR_DEPS = "DEPS")
load(":nhbazel/rules/docker-teamd.bzl", TEAMD_DEPS = "DEPS")

# Specs (deps/base/release) for every docker shared across platforms: the base DAG, the shared
# app dockers, and the two built-but-not-imaged standalones (iccpd, p4rt). Keyed by ':docker_x'
# label -- the form lib/prebuilt_tokens.bzl walks. Platform-specific specs live in the platform
# modules; the platform assembles docker_spec = SHARED_SPECS + its own for the token derivation.
SHARED_SPECS = {
    ":docker_base_trixie": struct(deps = BASE_TRIXIE_DEPS, base = None, release = "trixie"),
    ":docker_config_engine_trixie": struct(deps = CONFIG_ENGINE_TRIXIE_DEPS, base = ":docker_base_trixie", release = "trixie"),
    ":docker_swss_layer_trixie": struct(deps = SWSS_LAYER_TRIXIE_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_orchagent": struct(deps = ORCHAGENT_DEPS, base = ":docker_swss_layer_trixie", release = "trixie"),
    ":docker_dash_ha": struct(deps = DASH_HA_DEPS, base = ":docker_swss_layer_trixie", release = "trixie"),
    ":docker_fpm_frr": struct(deps = FPM_FRR_DEPS, base = ":docker_swss_layer_trixie", release = "trixie"),
    ":docker_macsec": struct(deps = MACSEC_DEPS, base = ":docker_swss_layer_trixie", release = "trixie"),
    ":docker_nat": struct(deps = NAT_DEPS, base = ":docker_swss_layer_trixie", release = "trixie"),
    ":docker_sflow": struct(deps = SFLOW_DEPS, base = ":docker_swss_layer_trixie", release = "trixie"),
    ":docker_teamd": struct(deps = TEAMD_DEPS, base = ":docker_swss_layer_trixie", release = "trixie"),
    ":docker_iccpd": struct(deps = ICCPD_DEPS, base = ":docker_swss_layer_trixie", release = "trixie"),
    ":docker_database": struct(deps = DATABASE_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_dhcp_relay": struct(deps = DHCP_RELAY_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_eventd": struct(deps = EVENTD_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_sonic_gnmi": struct(deps = SONIC_GNMI_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_gnmi_sidecar": struct(deps = GNMI_SIDECAR_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_gnmi_watchdog": struct(deps = GNMI_WATCHDOG_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_lldp": struct(deps = LLDP_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_mux": struct(deps = MUX_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_sonic_otel": struct(deps = SONIC_OTEL_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_sonic_p4rt": struct(deps = SONIC_P4RT_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_platform_monitor": struct(deps = PLATFORM_MONITOR_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_sonic_restapi": struct(deps = SONIC_RESTAPI_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_restapi_sidecar": struct(deps = RESTAPI_SIDECAR_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_restapi_watchdog": struct(deps = RESTAPI_WATCHDOG_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_router_advertiser": struct(deps = ROUTER_ADVERTISER_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_snmp": struct(deps = SNMP_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_sonic_mgmt_framework": struct(deps = SONIC_MGMT_FRAMEWORK_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_sysmgr": struct(deps = SYSMGR_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_sonic_bmp": struct(deps = SONIC_BMP_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
    ":docker_bmp_watchdog": struct(deps = BMP_WATCHDOG_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
}

# Base DAG roots the platform images pre-build (trixie-only: every broadcom + vs image docker
# derives from a trixie base). nhbazel builds no bookworm dockers -- the vs image chain is fully
# trixie, and docker-ptf (the last bookworm extra) moved to trixie in upstream #27889.
BASE_DOCKERS = [
    ":docker_base_trixie",
    ":docker_config_engine_trixie",
    ":docker_swss_layer_trixie",
]

# App dockers shared by the broadcom + vs images (swss-layer / config-engine children + the
# sidecar/watchdog auxiliaries + dash-ha + platform-monitor).
APP_DOCKERS = [
    ":docker_dash_ha",
    ":docker_orchagent",
    ":docker_teamd",
    ":docker_fpm_frr",
    ":docker_nat",
    ":docker_sflow",
    ":docker_macsec",
    ":docker_database",
    ":docker_snmp",
    ":docker_lldp",
    ":docker_dhcp_relay",
    ":docker_router_advertiser",
    ":docker_eventd",
    ":docker_mux",
    ":docker_sysmgr",
    ":docker_sonic_bmp",
    ":docker_sonic_restapi",
    ":docker_sonic_mgmt_framework",
    ":docker_sonic_otel",
    ":docker_bmp_watchdog",
    ":docker_restapi_sidecar",
    ":docker_restapi_watchdog",
    ":docker_gnmi_sidecar",
    ":docker_gnmi_watchdog",
    ":docker_sonic_gnmi",
    ":docker_platform_monitor",
]

# dbg derivations (stem, release, minimal): shared broadcom+vs, generated from their parent app
# docker. minimal=True -> the ci-pr subset (only-for-ci: orchagent, fpm-frr); the rest are
# only-for-nightly. syncd-brcm-dbg is broadcom-only (own file, platform SAI) and not here.
DBG = [
    ("docker-orchagent", "trixie", True),
    ("docker-fpm-frr", "trixie", True),
    ("docker-teamd", "trixie", False),
    ("docker-nat", "trixie", False),
    ("docker-sflow", "trixie", False),
    ("docker-macsec", "trixie", False),
    ("docker-database", "trixie", False),
    ("docker-snmp", "trixie", False),
    ("docker-lldp", "trixie", False),
    ("docker-dhcp-relay", "trixie", False),
    ("docker-router-advertiser", "trixie", False),
    ("docker-eventd", "trixie", False),
    ("docker-mux", "trixie", False),
    ("docker-sysmgr", "trixie", False),
    ("docker-sonic-bmp", "trixie", False),
    ("docker-bmp-watchdog", "trixie", False),
    ("docker-sonic-restapi", "trixie", False),
    ("docker-restapi-sidecar", "trixie", False),
    ("docker-restapi-watchdog", "trixie", False),
    ("docker-sonic-mgmt-framework", "trixie", False),
    ("docker-sonic-otel", "trixie", False),
    ("docker-sonic-gnmi", "trixie", False),
    ("docker-gnmi-sidecar", "trixie", False),
    ("docker-gnmi-watchdog", "trixie", False),
    ("docker-telemetry-watchdog", "trixie", False),
    ("docker-dash-ha", "trixie", False),
    ("docker-platform-monitor", "trixie", False),
    ("docker-stp", "trixie", False),
]

# The post-image makes a DBG row orders after, by stem.
DBG_AFTER = {
    # Not installed, so the image make never builds this parent: the docker-sonic-gnmi -dbg make
    # does ($(DOCKER_GNMI_DBG)_AFTER in rules/docker-gnmi.mk).
    "docker-telemetry-watchdog": [":docker_sonic_gnmi_dbg"],
}
