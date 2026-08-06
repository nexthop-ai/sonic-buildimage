import jinja2

from .log import log_err, log_info, log_warn
from .manager import Manager


class NhtMgr(Manager):
    """
    Manager for NEXTHOP_TRACKING table.
    Handles neighbor tracking (ARP/ND) configuration for FRR zebra.

    Table format: NEXTHOP_TRACKING|vrf_name|afi
    where vrf_name can be 'default' or a user VRF, and afi is 'ipv4' or 'ipv6'.
    """

    def __init__(self, common_objs, db, table):
        """
        Initialize the NhtMgr object.

        :param common_objs: common object dictionary
        :param db: name of the db
        :param table: name of the table in the db
        """
        super(NhtMgr, self).__init__(
            common_objs,
            [],
            db,
            table,
        )
        tf = common_objs['tf']
        self.nht_template = tf.from_file("zebra/zebra.nht.db.conf.j2")

    def set_handler(self, key, data):
        """
        Implementation of 'SET' command for NEXTHOP_TRACKING table.

        :param key: Key in format "vrf_name|afi" (e.g., "default|ipv4" or "Vrf_blue|ipv6")
        :param data: Dictionary with 'neighbor_tracking' field
        :return: True on success
        """
        # Parse and validate the composite key BEFORE any state mutation.
        # A malformed key must not pollute directory state, which is consumed
        # by dependency-resolution logic in other managers.
        key_parts = key.split('|')
        if len(key_parts) != 2:
            log_err("NhtMgr: invalid key format '%s', expected 'vrf_name|afi'" % key)
            return True

        vrf_name = key_parts[0]
        afi = key_parts[1]

        # Validate vrf_name: "|ipv4".split('|') yields ['', 'ipv4'] which
        # passes the length check but would render malformed config.
        if not vrf_name:
            log_err("NhtMgr: empty vrf_name in key '%s'" % key)
            return True

        # Validate AFI
        if afi not in ['ipv4', 'ipv6']:
            log_err("NhtMgr: invalid AFI '%s', expected 'ipv4' or 'ipv6'" % afi)
            return True

        # Get neighbor_tracking value (default to 'false')
        neighbor_tracking = data.get('neighbor_tracking', 'false')

        # Validate value: YANG enforces boolean at write time, but Redis can
        # receive direct writes. Reject anything outside the allow-list with a
        # warning rather than silently treating it as false.
        if neighbor_tracking not in ('true', 'false'):
            log_warn("NhtMgr: unexpected neighbor_tracking value '%s' for key '%s', treating as false" %
                     (neighbor_tracking, key))
            neighbor_tracking = 'false'

        # resolve_via_default: legacy runtime honors this for the default
        # VRF only -- per-VRF resolve is unified-mode (frrcfgd) only. The 'unset'
        # sentinel means "emit nothing" (field absent, or a user VRF). An absent
        # field is a no-op so a neighbor_tracking-only update never disturbs the
        # boot-time resolve-via-default state.
        resolve_via_default = data.get('resolve_via_default', 'unset')
        if resolve_via_default not in ('true', 'false'):
            if resolve_via_default != 'unset':
                log_warn("NhtMgr: unexpected resolve_via_default value '%s' for key '%s', ignoring" %
                         (resolve_via_default, key))
            resolve_via_default = 'unset'
        if vrf_name != 'default':
            resolve_via_default = 'unset'

        # Render template
        try:
            txt = self.nht_template.render(
                vrf_name=vrf_name,
                afi=afi,
                neighbor_tracking=neighbor_tracking,
                resolve_via_default=resolve_via_default
            )
        except jinja2.TemplateError as e:
            log_err("NhtMgr: error rendering template for key '%s': %s" % (key, str(e)))
            return True

        # Push configuration to FRR
        self.cfg_mgr.push(txt)

        # Record in directory only after the push has been queued -- avoids a
        # split-brain where the directory claims tracking is configured but
        # FRR never received the command (e.g., template render failure).
        self.directory.put(self.db_name, self.table_name, key, data)

        log_info("NhtMgr: neighbor_tracking=%s scheduled for (vrf=%s, afi=%s)" %
                 (neighbor_tracking, vrf_name, afi))

        if resolve_via_default != 'unset':
            log_info("NhtMgr: resolve_via_default=%s scheduled for (vrf=%s, afi=%s)" %
                     (resolve_via_default, vrf_name, afi))

        return True

    def del_handler(self, key):
        """
        Implementation of 'DEL' command for NEXTHOP_TRACKING table.

        :param key: Key in format "vrf_name|afi"
        :return: True on success
        """
        # Parse and validate the composite key BEFORE any state mutation.
        # Symmetric with set_handler: invalid keys must not perturb directory state.
        key_parts = key.split('|')
        if len(key_parts) != 2:
            log_err("NhtMgr: invalid key format '%s' on delete" % key)
            return True

        vrf_name = key_parts[0]
        afi = key_parts[1]

        # Validate vrf_name: "|ipv4".split('|') yields ['', 'ipv4'] which
        # passes the length check but would render malformed config.
        if not vrf_name:
            log_err("NhtMgr: empty vrf_name in key '%s' on delete" % key)
            return True

        # Validate AFI
        if afi not in ['ipv4', 'ipv6']:
            log_err("NhtMgr: invalid AFI '%s' on delete" % afi)
            return True

        # Render template with neighbor_tracking='false' to disable
        # Note: del_handler (row deleted) and set_handler(neighbor_tracking='false')
        # both emit "no ip nht arp-tracking" - the FRR effect is identical.
        # This is intentional: both represent "tracking disabled" state.
        # resolve_via_default: DELETE restores the YANG default (enabled) for the
        # default VRF so created-then-deleted matches never-created at runtime.
        # User-VRF resolve is unified-mode only, so it stays 'unset' (no-op) here.
        resolve_via_default = 'true' if vrf_name == 'default' else 'unset'
        try:
            txt = self.nht_template.render(
                vrf_name=vrf_name,
                afi=afi,
                neighbor_tracking='false',
                resolve_via_default=resolve_via_default
            )
        except jinja2.TemplateError as e:
            log_err("NhtMgr: error rendering template for delete key '%s': %s" % (key, str(e)))
            return True

        # Push configuration to FRR (disable tracking)
        self.cfg_mgr.push(txt)

        # Remove from directory only after the push has been queued -- avoids a
        # split-brain where the directory still claims tracking is configured
        # but FRR has already received the disable command.
        self.directory.remove(self.db_name, self.table_name, key)

        log_info("NhtMgr: neighbor_tracking disabled for (vrf=%s, afi=%s)" % (vrf_name, afi))

        return True
