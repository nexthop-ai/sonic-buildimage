"""SONiC aspeed image build macro (design.md §7.4).

Builds the aspeed ONIE image, `sonic-aspeed-arm64.bin` (platform/aspeed/one-image.mk:
`SONIC_ONE_IMAGE`, ARCH=arm64, MACHINE=aspeed). aspeed is the one bazel platform whose
CONFIGURED_ARCH is arm64 (PLATFORM_ARCH["aspeed"] in constants.bzl); the arch is threaded
through `:sonic_configure` (which runs `make configure PLATFORM=aspeed PLATFORM_ARCH=arm64`
-> arm64 slave container) so the image assembles natively in the arm64 slave.

The staged arm64 debs/wheels + the SONIC_COPY prebuilt flag + the fine-grained arm64
dockers all come from the "aspeed" membership table (sonic_image() derives them from
platform="aspeed", D6): the curated trixie subset plus the
aspeed-only sonic-redfish leaf. The flashable eMMC image is produced by a sibling genrule
(aspeed_emmc_image, below).
"""

load("//bazel_lib:log_utils.bzl", "log_setup")
load(":nhbazel/lib/active_rollout.bzl", "active_image", "active_staged", "active_token")
load(":nhbazel/lib/constants.bzl", "ASPEED_PACKAGES")
load(":nhbazel/lib/host_staging.bzl", "stage_host_roots")
load(":nhbazel/lib/image.bzl", "sonic_image")
load(":nhbazel/lib/platform_flag.bzl", "compatible_with_platform")
load(":nhbazel/lib/prebuilt_tokens.bzl", "platform_prebuilt_tokens")
load(":nhbazel/lib/release_utils.bzl", "bazel_prebuilt_make_arg", "bazel_prebuilt_wheels_make_arg")
load(":nhbazel/rules/bash.bzl", "BASH")
load(":nhbazel/rules/docker-shared.bzl", "SHARED_SPECS")
load(":nhbazel/rules/docker-sonic-redfish.bzl", SONIC_REDFISH_DEPS = "DEPS")
load(":nhbazel/rules/kdump-tools.bzl", "KDUMP_TOOLS")
load(":nhbazel/rules/linux-kernel.bzl", "KERNEL_PREBUILT_TOKEN")
load(":nhbazel/rules/makedumpfile.bzl", "MAKEDUMPFILE")
load(":nhbazel/rules/monit.bzl", "MONIT")
load(":nhbazel/rules/nhcli.bzl", "NHCLI")
load(":nhbazel/rules/openssh.bzl", "OPENSSH")
load(":nhbazel/rules/radius.bzl", "RADIUS")
load(":nhbazel/rules/sedutil.bzl", "SEDUTIL")
load(":nhbazel/rules/sonic-ctrmgrd-rs.bzl", "SONIC_CTRMGRD_RS")
load(":nhbazel/rules/sonic-ctrmgrd.bzl", "SONIC_CTRMGRD")
load(":nhbazel/rules/sonic-fib.bzl", "LIBFIB")
load(":nhbazel/rules/sonic-host-services-rs.bzl", "SONIC_HOST_SERVICES_RS")
load(":nhbazel/rules/sonic-host-services.bzl", "SONIC_HOST_SERVICES")
load(":nhbazel/rules/sonic-host-userd.bzl", "SONIC_HOST_USERD")
load(":nhbazel/rules/sonic-nettools.bzl", "SONIC_NETTOOLS")
load(":nhbazel/rules/sonic-utilities.bzl", "SONIC_UTILITIES")
load(":nhbazel/rules/syslog-counter.bzl", "SYSLOG_COUNTER")
load(":nhbazel/rules/system-health.bzl", "SYSTEM_HEALTH")
load(":nhbazel/rules/systemd-sonic-generator.bzl", "SYSTEMD_SONIC_GENERATOR")
load(":nhbazel/rules/tacacs.bzl", "TACACS")

# aspeed is arm64, trixie-only (RELEASE_PLATFORMS).
_RELEASES = ["trixie"]

# NOBOOKWORM=1: aspeed is trixie-only, but the top-level Makefile defaults NOBOOKWORM=0 so every
# build runs a bookworm stage first -- a no-op for aspeed (nothing bookworm-scoped) that only spins
# up the slave. Skip it, like broadcom. (aspeed_emmc/_all consume the .bin, so only aspeed_default,
# which runs the release loop, needs the flag.)
_NO_BOOKWORM = "NOBOOKWORM=1"

# arm64-reuse allowlist: a package is aspeed-compatible (staged for reuse) iff in ASPEED_PACKAGES
# (default_compat_for_pkg's rule, platform_flag.bzl); a token not in it is rebuilt inline for
# arm64, so it is not a reroute token. Reroute tokens are hyphenated / ASPEED_PACKAGES underscored.
_ASPEED_ALLOW = {p: True for p in ASPEED_PACKAGES}

def _aspeed_reuses(token):
    return bool(_ASPEED_ALLOW.get(token.replace("-", "_")))

# Host-rootfs staged packages (arm64). Adding a host deb = append here.
HOST_ROOTS = [
    BASH,
    KDUMP_TOOLS,
    LIBFIB,
    MAKEDUMPFILE,
    MONIT,
    NHCLI,
    OPENSSH,
    RADIUS,
    SEDUTIL,
    SONIC_CTRMGRD,
    SONIC_CTRMGRD_RS,
    SONIC_HOST_SERVICES,
    SONIC_HOST_SERVICES_RS,
    SONIC_HOST_USERD,
    SONIC_NETTOOLS,
    SONIC_UTILITIES,
    SYSLOG_COUNTER,
    SYSTEMD_SONIC_GENERATOR,
    SYSTEM_HEALTH,
    TACACS,
]

# The curated trixie subset of shared dockers aspeed's image pre-builds + its own sonic-redfish
# (not COMMON + delta -- aspeed disables most INCLUDE_* features, so it's an explicit subset).
ASPEED_IMAGE = [
    ":docker_base_trixie",
    ":docker_config_engine_trixie",
    ":docker_database",
    ":docker_lldp",
    ":docker_platform_monitor",
    ":docker_sonic_gnmi",
    ":docker_sysmgr",
    ":docker_sonic_redfish",
]

# Docker specs for the token walk = shared specs + aspeed's own sonic-redfish.
_ASPEED_SPECS = {
    ":docker_sonic_redfish": struct(deps = SONIC_REDFISH_DEPS, base = ":docker_config_engine_trixie", release = "trixie"),
}
DOCKER_SPEC = {k: v for d in [SHARED_SPECS, _ASPEED_SPECS] for k, v in d.items()}

def aspeed_prebuilt_tokens(compat = False):
    """The derived (deb, wheel) reroute token lists for aspeed, filtered to the arm64-reuse
    allowlist (a token aspeed rebuilds inline is not a reroute token)."""
    active = active_image(ASPEED_IMAGE)
    return struct(
        debs = platform_prebuilt_tokens(HOST_ROOTS, active, DOCKER_SPEC, "deb", _RELEASES, reuse_filter = _aspeed_reuses, host_token_filter = active_token, include_build_deps = compat),
        wheels = platform_prebuilt_tokens(HOST_ROOTS, active, DOCKER_SPEC, "wheel", _RELEASES, reuse_filter = _aspeed_reuses, host_token_filter = active_token, include_build_deps = compat),
    )

def aspeed_prebuilt_flag():
    """The NHBAZEL_PREBUILT_{DEBS,WHEELS} make-arg string for the aspeed image.

    KERNEL_PREBUILT_TOKEN is injected so the image make COPIES the staged (arm64) kernel debs
    instead of recompiling them inline (LINUX_HEADERS has token=None, so it's not in the walk)."""
    t = aspeed_prebuilt_tokens()
    return bazel_prebuilt_make_arg(t.debs + [KERNEL_PREBUILT_TOKEN]) + bazel_prebuilt_wheels_make_arg(t.wheels)

def aspeed_artifacts():
    """Stage aspeed's host-roots closure (:sonic_aspeed_artifacts, arm64-reuse filtered)."""
    stage_host_roots("sonic_aspeed_artifacts", HOST_ROOTS, _RELEASES, reuse_filter = _aspeed_reuses, token_filter = active_token)

def aspeed_image(debug = False):
    """One genrule producing `sonic-aspeed-arm64.bin` (`//sonic-buildimage:aspeed_default`).

    The arm64 arch comes from `.arch` (written by :sonic_configure); PLATFORM is not passed on
    the make line -- the build relies on the on-disk .platform. Returns the genrule label.
    """
    return sonic_image(
        name = "aspeed_default",
        make_target = "target/sonic-aspeed-arm64.bin",
        image_srcs = ["target/sonic-aspeed-arm64.bin"],
        platform = ["aspeed"],
        # aspeed's curated arm64 docker subset (active view) + its reuse-filtered prebuilt flag.
        docker_deps = active_staged(ASPEED_IMAGE),
        prebuilt = aspeed_prebuilt_flag(),
        log = "sonic-aspeed-arm64-bin.log",
        banner = "SONiC aspeed image (arm64)",
        extra_make_vars = _NO_BOOKWORM,
        # NO_SCCACHE=1 for the arm64 slave. Do NOT set NH_DISABLE_LIBYANG3_DEV_DONE=y here: aspeed
        # (unlike the other platforms) builds part of the libyang closure from source, so the
        # libyang3-dev-before-libyang-v1 sequencing must stay ON or nhcli links the wrong libyang.
        env_prefix = "NO_SCCACHE=1",
        # Debug flavor -> aspeed_default_debug (INSTALL_DEBUG_TOOLS=y baked in).
        debug = debug,
    )

def aspeed_emmc_image():
    """The eMMC installer image + the `:aspeed_default_all` main-lane bundle.

    `:aspeed_emmc` mirrors the broadcom syncd-rpc post-build pattern: a genrule that consumes
    the already-built image (`:aspeed_default` -> sonic-aspeed-arm64.bin) and produces an extra
    artifact, here the flashable eMMC disk image `sonic-aspeed-arm64-emmc.img.gz`
    (platform/aspeed/build-emmc-image-installer.sh, AST2700).

    Because it depends on `:aspeed_default`, building either `:aspeed_emmc` or the
    `:aspeed_default_all` filegroup builds the .bin first, then the eMMC image, in one bazel
    invocation. builder.py routes aspeed to `:aspeed_default_all` so both artifacts land.

    Needs root (loop-device mount, sgdisk, mkfs.ext4) so it runs local + unsandboxed via sudo.
    """
    native.genrule(
        name = "aspeed_emmc",
        visibility = ["//visibility:public"],
        srcs = [
            # The freshly-built image; also forces aspeed_default to run first.
            ":aspeed_default",
        ] + native.glob([
            "platform/aspeed/**",  # build-emmc-image-installer.sh, install-sonic-to-emmc.sh, onie-image-arm64.conf
        ], exclude = [
            "**/*:*",  # Bazel-invalid names
        ]),
        outs = ["sonic-aspeed-arm64-emmc.img.gz"],
        cmd = log_setup("sonic-aspeed-arm64-emmc.log", output_to_build_log = True) + """
        SONIC_DIR="$$(realpath sonic-buildimage)"
        # Resolve the Bazel output path to ABSOLUTE before cd'ing into SONIC_DIR below -- the
        # location() output path is relative to the execroot, so it would not resolve after the
        # cd (cp ... No such file or directory).
        OUT="$$(realpath -m "$(location sonic-aspeed-arm64-emmc.img.gz)")"
        echo "=== Building SONiC aspeed eMMC image (arm64) ==="
        cd "$$SONIC_DIR"

        # Stage the eMMC installer helper alongside the .bin (uploaded with target/).
        cp platform/aspeed/install-sonic-to-emmc.sh target/

        # build-emmc-image-installer.sh uses relative target/ paths and needs root (loop-device
        # mount / sgdisk / mkfs.ext4), so run it from SONIC_DIR under sudo -- the .bin was written
        # to target/ by :aspeed_default (local, unsandboxed).
        sudo bash platform/aspeed/build-emmc-image-installer.sh \
            target/sonic-aspeed-arm64.bin target/sonic-aspeed-arm64-emmc.img.gz

        cp "$$SONIC_DIR/target/sonic-aspeed-arm64-emmc.img.gz" "$$OUT"
        echo "=== SONiC aspeed eMMC image build complete ==="
""",
        # only-for-nightly: the eMMC image is a nightly-only artifact, so ci-pr's `:all` must not
        # build it. The bundle below carries the same tag (like broadcom_dbg_full) so ci-pr can't
        # pull it back in via the filegroup dep; the plain image (:aspeed_default) stays untagged
        # and still builds in every lane.
        tags = ["not-for-ci", "no-sandbox", "no-remote-cache", "only-for-nightly"],
        target_compatible_with = compatible_with_platform(["aspeed"]),
        local = True,
    )

    # Nightly-lane bundle: on ci-te the .bin and the eMMC image are produced in one invocation
    # (aspeed has no post-build phase). only-for-nightly so ci-pr's `:all` pattern does not pull
    # :aspeed_emmc through this filegroup dep (a dep bypasses the target's own tag filter). The
    # image itself is :aspeed_default (untagged), which ci-pr's `:all` still builds directly.
    native.filegroup(
        name = "aspeed_default_all",
        srcs = [":aspeed_default", ":aspeed_emmc"],
        visibility = ["//visibility:public"],
        tags = ["not-for-ci", "only-for-nightly"],
        target_compatible_with = compatible_with_platform(["aspeed"]),
    )
    return ":aspeed_default_all"
