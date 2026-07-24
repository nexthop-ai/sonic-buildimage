"""Shared pytest helpers for frrcfgd unit tests."""


def render_vtysh_cmd(cmd):
    """Render an argv-list vtysh command back to its shell-string form."""
    if not isinstance(cmd, list):
        return cmd
    out = []
    i = 0
    while i < len(cmd):
        if cmd[i] == '-c' and i + 1 < len(cmd):
            out.append("-c '%s'" % cmd[i + 1])
            i += 2
        else:
            out.append(cmd[i])
            i += 1
    return ' '.join(out)
