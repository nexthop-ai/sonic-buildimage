# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RTC sync interface shared by RTC-capable platform devices and the rtc_sync util."""

import abc


class RTCSyncable(abc.ABC):

    @abc.abstractmethod
    def rtc_sync(self) -> bool:
        """Synchronizes this device's RTC with the current system time.

        Returns True if the sync succeeded.
        """
