#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from sonic_platform_base.sonic_thermal_control.thermal_condition_base import ThermalPolicyConditionBase
from sonic_platform_base.sonic_thermal_control.thermal_json_object import thermal_json_object
from .thermal_infos import FanDrawerInfo, ThermalInfo

class FanDrawerCondition(ThermalPolicyConditionBase):
    def get_fan_drawer_info(self, thermal_info_dict) -> FanDrawerInfo | None:
        """
        Get fan info from thermal dict to determine
        if a fan condition matches
        """
        return thermal_info_dict.get(FanDrawerInfo.INFO_TYPE)

@thermal_json_object('fandrawer.one.present')
class FanDrawerOnePresentCondition(FanDrawerCondition):
    """
    Condition if one fan drawer is present
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 1

@thermal_json_object('fandrawer.two.present')
class FanDrawerTwoPresentCondition(FanDrawerCondition):
    """
    Condition if two fan drawers are present
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 2

@thermal_json_object('fandrawer.three.present')
class FanDrawerThreePresentCondition(FanDrawerCondition):
    """
    Condition if three fan drawers are present
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 3

@thermal_json_object('fandrawer.four.present')
class FanDrawerFourPresentCondition(FanDrawerCondition):
    """
    Condition if four fan drawers are present
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 4

@thermal_json_object('fandrawer.five.present')
class FanDrawerFivePresentCondition(FanDrawerCondition):
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 5

@thermal_json_object('fandrawer.six.present')
class FanDrawerSixPresentCondition(FanDrawerCondition):
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 6

@thermal_json_object('fandrawer.seven.present')
class FanDrawerSevenPresentCondition(FanDrawerCondition):
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 7

@thermal_json_object('fandrawer.eight.present')
class FanDrawerEightPresentCondition(FanDrawerCondition):
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 8

@thermal_json_object('default.operation')
class ThermalControlAlgorithmCondition(FanDrawerCondition):
    """
    Default case when more than two fan drawers are present
    """
    def is_match(self, thermal_info_dict):
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
<<<<<<< HEAD
        return fan_drawer_info.get_num_present_fan_drawers() > 2
=======
        return fan_drawer_info.get_num_functional_fan_drawers() > 2


@thermal_json_object('temperature.any_over_critical')
class TemperatureOverCriticalCondition(ThermalPolicyConditionBase):
    """
    Case when a temperature sensor exceeds the software shutdown threshold.
    """
    def is_match(self, thermal_info_dict):
        thermal_info: ThermalInfo = thermal_info_dict[ThermalInfo.INFO_TYPE]
        overtemp = thermal_info.get_sw_overtemperature_thermals()
        return len(overtemp) > 0
>>>>>>> dd8dc246b (NOS-3746: Software thermal powercycle (#6009))
