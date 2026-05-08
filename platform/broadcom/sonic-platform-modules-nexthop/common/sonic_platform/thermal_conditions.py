#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from sonic_platform_base.sonic_thermal_control.thermal_condition_base import ThermalPolicyConditionBase
from sonic_platform_base.sonic_thermal_control.thermal_json_object import thermal_json_object
from .thermal_infos import FanDrawerInfo

class FanDrawerCondition(ThermalPolicyConditionBase):
    def get_fan_drawer_info(self, thermal_info_dict) -> FanDrawerInfo:
        """
        Get fan info from thermal dict to determine
        if a fan condition matches
        """
        return thermal_info_dict.get(FanDrawerInfo.INFO_TYPE)

@thermal_json_object('fandrawer.one.functional')
class FanDrawerOneFunctionalCondition(FanDrawerCondition):
    """
    Condition if exactly one fan drawer is functional (present and all fans healthy)
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() == 1

@thermal_json_object('fandrawer.two.functional')
class FanDrawerTwoFunctionalCondition(FanDrawerCondition):
    """
    Condition if exactly two fan drawers are functional (present and all fans healthy)
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() == 2

@thermal_json_object('fandrawer.three.functional')
class FanDrawerThreeFunctionalCondition(FanDrawerCondition):
    """
    Condition if exactly three fan drawers are functional (present and all fans healthy)
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() == 3

@thermal_json_object('fandrawer.four.functional')
class FanDrawerFourFunctionalCondition(FanDrawerCondition):
    """
    Condition if exactly four fan drawers are functional (present and all fans healthy)
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() == 4

@thermal_json_object('fandrawer.five.functional')
class FanDrawerFiveFunctionalCondition(FanDrawerCondition):
    """
    Condition if exactly five fan drawers are functional (present and all fans healthy)
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() == 5

@thermal_json_object('fandrawer.six.functional')
class FanDrawerSixFunctionalCondition(FanDrawerCondition):
    """
    Condition if exactly six fan drawers are functional (present and all fans healthy)
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() == 6

@thermal_json_object('fandrawer.seven.functional')
class FanDrawerSevenFunctionalCondition(FanDrawerCondition):
    """
    Condition if exactly seven fan drawers are functional (present and all fans healthy)
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() == 7

@thermal_json_object('fandrawer.eight.functional')
class FanDrawerEightFunctionalCondition(FanDrawerCondition):
    """
    Condition if exactly eight fan drawers are functional (present and all fans healthy)
    """
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() == 8

@thermal_json_object('fandrawer.four.present')
class FanDrawerFourPresentCondition(FanDrawerCondition):
    def is_match(self, thermal_info_dict: dict) -> bool:
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_present_fan_drawers() == 4
    
@thermal_json_object('default.operation')
class ThermalControlAlgorithmCondition(FanDrawerCondition):
    """
    Default case when more than two fan drawers are functional
    """
    def is_match(self, thermal_info_dict):
        fan_drawer_info = self.get_fan_drawer_info(thermal_info_dict)
        return fan_drawer_info.get_num_functional_fan_drawers() > 2
