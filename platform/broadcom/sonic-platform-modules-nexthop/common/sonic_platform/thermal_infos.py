#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import NamedTuple

from sonic_platform_base.sonic_thermal_control.thermal_info_base import ThermalPolicyInfoBase
from sonic_platform_base.sonic_thermal_control.thermal_json_object import thermal_json_object

# For reference where these items come from
from .chassis import Chassis
from .thermal import Thermal
from .thermal_manager import ThermalManager
from .fan import Fan
from .fan_drawer import FanDrawer
from .psu import Psu


class OvertemperatureSensor(NamedTuple):
    thermal: Thermal
    temperature: float
    """The current temperature of the sensor."""
    threshold: float
    """The threshold that the sensor has violated."""


@thermal_json_object('fan_drawer_info')
class FanDrawerInfo(ThermalPolicyInfoBase):
    """Fan information for all fan drawers"""
    INFO_TYPE = 'fan_drawer_info'
    def __init__(self):
        self._fans = []
        self._fan_drawers = []
    
    def collect(self, chassis: Chassis):
        self._fans = chassis.get_all_fans()[:]
        self._fan_drawers = chassis.get_all_fan_drawers()[:]

    def get_fans(self)->list[Fan]:
        return self._fans

    def get_fan_drawers(self)->list[FanDrawer]:
        return self._fan_drawers
    
    def get_num_present_fan_drawers(self):
        return sum([fan_drawer.get_presence() for fan_drawer in self._fan_drawers])
    
@thermal_json_object('thermal_info')
class ThermalInfo(ThermalPolicyInfoBase):
    INFO_TYPE = 'thermal_info'
    def __init__(self):
        self._thermals = []
        self._thermal_manager = None
        self._sw_overtemp_thermals = None
    
    def collect(self, chassis: Chassis):
        self._thermals = chassis.get_all_thermals()[:]
        for sfp in chassis.get_all_sfps():
            self._thermals.extend(sfp.get_all_thermals())
        self._thermal_manager = chassis.get_thermal_manager()
        # when we call collect() at the start of the loop, refresh overtemperature sensors
        self._sw_overtemp_thermals = None
    
    def get_thermals(self) -> list[Thermal]:
        return self._thermals
    
    def get_thermal_manager(self) -> ThermalManager:
        return self._thermal_manager

    def get_sw_overtemperature_thermals(self) -> list[OvertemperatureSensor]:
        """
        Get a list of all thermals that are over their sw_reboot_threshold.
        
        Returns:
            A list of sensors that are overtemperature, along with their current temperature and threshold.
        """
        # cache this list between calls in the same loop so that condition and action has the same list
        if self._sw_overtemp_thermals is not None:
            return self._sw_overtemp_thermals

        overtemp: list[OvertemperatureSensor] = []
        for thermal in self.get_thermals():
            try:
                threshold = thermal.get_sw_reboot_threshold()
                if threshold is None:
                    continue
                temperature = thermal.get_temperature()
                if temperature is not None and temperature > threshold:
                    overtemp.append(OvertemperatureSensor(thermal, temperature, threshold))
            except Exception:
                pass

        self._sw_overtemp_thermals = overtemp
        return overtemp

@thermal_json_object('psu_info')
class PsuInfo(ThermalPolicyInfoBase):
    """PSUs have separate fans and thermals from the chassis"""
    INFO_TYPE = 'psu_info'
    def __init__(self):
        self._psus = []
    
    def collect(self, chassis: Chassis):
        self._psus = chassis.get_all_psus()[:]
    
    def get_thermals(self)->list:
        thermals = []
        for psu in self._psus:
            thermals.extend(psu.get_all_thermals())
        return thermals

    def get_fans(self)->list:
        fans = []
        for psu in self._psus:
            fans.extend(psu.get_all_fans())
        return fans

@thermal_json_object('chassis_info')
class ChassisInfo(ThermalPolicyInfoBase):
    """Give raw access to the chassis"""
    INFO_TYPE = 'chassis_info'
    def __init__(self):
        self._chassis = None
    
    def collect(self, chassis: Chassis):
        self._chassis = chassis
    
    def get_chassis(self) -> Chassis:
        assert self._chassis
        return self._chassis
