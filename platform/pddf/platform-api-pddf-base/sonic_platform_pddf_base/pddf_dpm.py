#############################################################################
# PDDF
#
# PDDF DPM base class inherited from the base class
#############################################################################


try:
    from sonic_platform_base.dpm_base import DpmBase
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sonic_platform_pddf_base.pddfapi import PddfApi


class PddfDpm(DpmBase):
    """PDDF generic DPM class (thin: identity + hierarchy anchor)"""

    pddf_obj: "PddfApi"
    plugin_data: dict

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        DpmBase.__init__(self)
        if not pddf_data or not pddf_plugin_data:
            raise ValueError('PDDF JSON data error')

        self.pddf_obj = pddf_data
        self.plugin_data = pddf_plugin_data
        self.platform = self.pddf_obj.get_platform()

        self.dpm_index = index # 0-indexed
        self.dpm_obj_name = "DPM{0}".format(self.dpm_index + 1) # device entries are 1-indexed
        self.dpm_obj = self.pddf_obj.data[self.dpm_obj_name]

    def get_name(self):
        """
        Retrieves the name of the device

        Returns:
            string: The name of the device
        """
        return self.dpm_obj_name

    def get_presence(self):
        """
        Retrieves the presence of the device

        DPMs are onboard, non-removable devices, so they are always present.
        Platforms with detectable DPMs may override this.

        Returns:
            bool: True if device is present, False if not
        """
        return True
