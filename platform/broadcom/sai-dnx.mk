# Broadcom DNX SAI definitions
# Nexthop-CUSTOM DNX SAI: built from nhbroadcomsai/sonic-dnx (private-bcm-sai-sonic,
# NH_SAI_15.2.0_GA) against the GA HSDK (KCOM_VERSION 24) and published to the
# nh-custom-sai S3 bucket. Replaces the stock upstream libsaibcm_dnx
# (15.2.0.0.0.0.3.1, SDK 6.5.35-SP1, KCOM != 24), which mismatched the KCOM-24
# kernel modules built from saibcm-modules-dnx and lacked Nexthop Q3D/NH-5010 support.
LIBSAIBCM_DNX_VERSION = 15.2.0.0.0.0.0.0

LIBSAIBCM_DNX_URL_PREFIX = "https://nh-custom-sai.s3.us-east-2.amazonaws.com/$(LIBSAIBCM_DNX_VERSION)/dnx_v1"

# SAI module for DNX Asic family
BRCM_DNX_SAI = libsaibcm_dnx_$(LIBSAIBCM_DNX_VERSION)_amd64.deb
$(BRCM_DNX_SAI)_URL = "$(LIBSAIBCM_DNX_URL_PREFIX)/$(BRCM_DNX_SAI)"

# Package registration
SONIC_ONLINE_DEBS += $(BRCM_DNX_SAI)

# Version handling
$(BRCM_DNX_SAI)_SKIP_VERSION=y
