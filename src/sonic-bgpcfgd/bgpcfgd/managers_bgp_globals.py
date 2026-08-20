from swsscommon import swsscommon

from .log import log_info, log_warn
from .manager import Manager

BGP_GLOBALS_TABLE = "BGP_GLOBALS"


class BgpGlobalsMgr(Manager):
    """Handles runtime changes to BGP_GLOBALS|default in ConfigDB.

    Presence of llgr_stale_time enables LLGR; absence disables it (RFC 9494).
      bgp long-lived-graceful-restart stale-time <N>   (enable)
      no bgp long-lived-graceful-restart stale-time    (disable)

    Presence of gr_select_defer_time sets the GR select-defer timer;
    absence clears it.
      bgp graceful-restart select-defer-time <N>       (set)
      no bgp graceful-restart select-defer-time        (clear)

    graceful_restart_enable and graceful_shutdown are booleans rather than
    presence/absence: 'true' enables, anything else (including absence)
    disables. These mirror the BGP_GLOBALS knobs frrcfgd handles in unified
    mode, so the same CONFIG_DB works under either mode.
      bgp graceful-restart                             (enable, RFC 4724)
      no bgp graceful-restart                          (disable)
      bgp graceful-shutdown                            (enable, RFC 8326)
      no bgp graceful-shutdown                         (disable)

    Only the 'default' VRF key is handled; other VRF keys are ignored.
    """

    def __init__(self, common_objs, db, table):
        super(BgpGlobalsMgr, self).__init__(
            common_objs,
            [("CONFIG_DB", swsscommon.CFG_DEVICE_METADATA_TABLE_NAME, "localhost/bgp_asn")],
            db,
            table,
        )
        self._llgr_active = False
        self._select_defer_active = False
        self._gr_active = False
        self._graceful_shutdown_active = False

    def set_handler(self, key, data):
        if key != "default":
            log_info("BgpGlobalsMgr: ignoring non-default VRF key '%s'" % key)
            return True

        bgp_asn = self.get_bgp_asn()
        if bgp_asn is None:
            log_info("BgpGlobalsMgr: no BGP ASN found, deferring")
            return False

        stale_time = data.get("llgr_stale_time")
        if stale_time is not None:
            cmds = self._build_llgr_enable_cmds(bgp_asn, stale_time)
            log_info("BgpGlobalsMgr: enabling LLGR stale-time=%s" % stale_time)
            self.cfg_mgr.push_list(cmds)
            self._llgr_active = True
        else:
            # Always send the no command — it is idempotent in FRR and closes the
            # crash-recovery window where bgpcfgd died after an operator removed
            # llgr_stale_time but before the disable command reached FRR.
            cmds = self._build_llgr_disable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: disabling LLGR")
            self.cfg_mgr.push_list(cmds)
            self._llgr_active = False

        defer_time = data.get("gr_select_defer_time")
        if defer_time is not None:
            cmds = self._build_select_defer_enable_cmds(bgp_asn, defer_time)
            log_info("BgpGlobalsMgr: setting GR select-defer-time=%s" % defer_time)
            self.cfg_mgr.push_list(cmds)
            self._select_defer_active = True
        else:
            cmds = self._build_select_defer_disable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: clearing GR select-defer-time")
            self.cfg_mgr.push_list(cmds)
            self._select_defer_active = False

        # Booleans, not presence/absence: an absent key means "not configured",
        # which is the same desired state as an explicit 'false'. As above, the
        # command is sent unconditionally because it is idempotent in FRR and
        # closes the crash-recovery window.
        gr_enabled = str(data.get("graceful_restart_enable", "false")).lower() == "true"
        if gr_enabled:
            cmds = self._build_gr_enable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: enabling graceful-restart")
        else:
            cmds = self._build_gr_disable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: disabling graceful-restart")
        self.cfg_mgr.push_list(cmds)
        self._gr_active = gr_enabled

        gshut_enabled = str(data.get("graceful_shutdown", "false")).lower() == "true"
        if gshut_enabled:
            cmds = self._build_graceful_shutdown_enable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: enabling graceful-shutdown")
        else:
            cmds = self._build_graceful_shutdown_disable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: disabling graceful-shutdown")
        self.cfg_mgr.push_list(cmds)
        self._graceful_shutdown_active = gshut_enabled

        return True

    def del_handler(self, key):
        if key != "default":
            return

        bgp_asn = self.get_bgp_asn()
        if bgp_asn is None:
            log_warn("BgpGlobalsMgr: no BGP ASN on delete, clearing state")
            self._llgr_active = False
            self._select_defer_active = False
            self._gr_active = False
            self._graceful_shutdown_active = False
            return

        if self._llgr_active:
            cmds = self._build_llgr_disable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: disabling LLGR (entry deleted)")
            self.cfg_mgr.push_list(cmds)
            self._llgr_active = False

        if self._select_defer_active:
            cmds = self._build_select_defer_disable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: clearing GR select-defer-time (entry deleted)")
            self.cfg_mgr.push_list(cmds)
            self._select_defer_active = False

        if self._gr_active:
            cmds = self._build_gr_disable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: disabling graceful-restart (entry deleted)")
            self.cfg_mgr.push_list(cmds)
            self._gr_active = False

        if self._graceful_shutdown_active:
            cmds = self._build_graceful_shutdown_disable_cmds(bgp_asn)
            log_info("BgpGlobalsMgr: disabling graceful-shutdown (entry deleted)")
            self.cfg_mgr.push_list(cmds)
            self._graceful_shutdown_active = False

    @staticmethod
    def _build_llgr_enable_cmds(bgp_asn, stale_time):
        return [
            "router bgp %s" % bgp_asn,
            " bgp long-lived-graceful-restart stale-time %s" % stale_time,
            "exit",
        ]

    @staticmethod
    def _build_llgr_disable_cmds(bgp_asn):
        return [
            "router bgp %s" % bgp_asn,
            " no bgp long-lived-graceful-restart stale-time",
            "exit",
        ]

    @staticmethod
    def _build_select_defer_enable_cmds(bgp_asn, defer_time):
        return [
            "router bgp %s" % bgp_asn,
            " bgp graceful-restart select-defer-time %s" % defer_time,
            "exit",
        ]

    @staticmethod
    def _build_select_defer_disable_cmds(bgp_asn):
        return [
            "router bgp %s" % bgp_asn,
            " no bgp graceful-restart select-defer-time",
            "exit",
        ]

    @staticmethod
    def _build_gr_enable_cmds(bgp_asn):
        return [
            "router bgp %s" % bgp_asn,
            " bgp graceful-restart",
            "exit",
        ]

    @staticmethod
    def _build_gr_disable_cmds(bgp_asn):
        return [
            "router bgp %s" % bgp_asn,
            " no bgp graceful-restart",
            "exit",
        ]

    @staticmethod
    def _build_graceful_shutdown_enable_cmds(bgp_asn):
        return [
            "router bgp %s" % bgp_asn,
            " bgp graceful-shutdown",
            "exit",
        ]

    @staticmethod
    def _build_graceful_shutdown_disable_cmds(bgp_asn):
        return [
            "router bgp %s" % bgp_asn,
            " no bgp graceful-shutdown",
            "exit",
        ]
