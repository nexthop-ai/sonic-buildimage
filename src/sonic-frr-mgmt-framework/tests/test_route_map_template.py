"""
Golden-file tests for bgpd.conf.db.route_map.j2 and bgpd.conf.db.comm_list.j2.

Covers everything changed in this round of work:
- set_ext_community_inline / set_community_inline / set_large_community_inline
  regression: these three leaf-lists used to be gated on a stale 'field@' key
  with .split(','), which sonic-cfggen -d never actually produces (it already
  hands templates a plain 'field' key holding a real list) -- the blocks
  silently rendered nothing at cold-boot. Now fixed to key on the plain field
  name and iterate the list directly.
- color extended-community support in set_ext_community_inline (mixed with rt)
  and in EXTENDED_COMMUNITY_SET.community_member (STANDARD set_type).
- match_ext_community_mode (exact-match/any optional modifier).
- match_ext_community_limit.
- set_ext_community_delete.
- EXPANDED set_type community_member remains raw passthrough, untouched by
  any of the above (regression guard).

Rendered with trim_blocks=True to match sonic-cfggen's actual Jinja
environment (the production renderer for this template at cold boot),
per the pathd.conf.j2 test convention already in this file's sibling.
"""

import os

from jinja2 import Environment, FileSystemLoader


def _template_env():
    template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'bgpd')
    return Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)


def _render_route_map(route_map_data):
    env = _template_env()
    template = env.get_template('bgpd.conf.db.route_map.j2')
    return template.render(ROUTE_MAP=route_map_data)


def _render_comm_list(extended_community_set_data):
    env = _template_env()
    template = env.get_template('bgpd.conf.db.comm_list.j2')
    return template.render(EXTENDED_COMMUNITY_SET=extended_community_set_data)


def _load_fixture(name):
    fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'route_map', name + '.conf')
    with open(fixture_path) as f:
        return f.read()


def test_route_map_full_statement_matches_golden():
    """Comprehensive statement: match mode+limit, set community/ext-community
    (rt+color mixed)/large-community, set_ext_community_delete. Exercises the
    field@ -> field regression fix and every new leaf in one pass."""
    result = _render_route_map({
        ('POLICY', '10'): {
            'route_operation': 'permit',
            'match_ext_community': 'COLOR_SET',
            'match_ext_community_mode': 'EXACT_MATCH',
            'match_ext_community_limit': 3,
            'set_community_inline': ['65000:1', '65000:2'],
            'set_ext_community_inline': ['route-target:65000:1', 'color:00:100'],
            'set_large_community_inline': ['65000:1:1'],
            'set_ext_community_delete': 'OLD_SET',
        }
    })
    assert result == _load_fixture('full_statement')


def test_route_map_none_clears_all_ext_community():
    result = _render_route_map({
        ('POLICY', '10'): {
            'route_operation': 'permit',
            'set_ext_community_inline': ['none'],
        }
    })
    assert result == _load_fixture('none_clears')
    assert 'set extcommunity rt' not in result
    assert 'set extcommunity color' not in result


def test_route_map_match_ext_community_bare_no_modifier():
    """No match_ext_community_mode/limit present -> bare form, no trailing
    'exact-match'/'any', no extcommunity-limit line."""
    result = _render_route_map({
        ('POLICY', '20'): {
            'route_operation': 'permit',
            'match_ext_community': 'COLOR_SET',
        }
    })
    assert result == _load_fixture('match_bare')
    assert 'exact-match' not in result
    assert 'extcommunity-limit' not in result


def test_route_map_match_ext_community_any_and_limit():
    result = _render_route_map({
        ('POLICY', '30'): {
            'route_operation': 'permit',
            'match_ext_community': 'COLOR_SET',
            'match_ext_community_mode': 'ANY',
            'match_ext_community_limit': 5,
        }
    })
    assert result == _load_fixture('match_any_limit')


def test_comm_list_standard_any_color():
    result = _render_comm_list({
        'COLOR_SET': {'set_type': 'STANDARD', 'match_action': 'ANY',
                      'community_member': ['color:00:100']},
    })
    assert result == _load_fixture('comm_list_standard_any_color')


def test_comm_list_standard_all_mixed_rt_and_color():
    """ALL match_action combines every member into a single permit line,
    mixing rt and color markers -- confirmed valid on real FRR (single
    extcommunity-list entry can mix keyword-tagged tokens)."""
    result = _render_comm_list({
        'MIX_SET': {'set_type': 'STANDARD', 'match_action': 'ALL',
                    'community_member': ['route-target:65000:1', 'color:00:100']},
    })
    assert result == _load_fixture('comm_list_standard_all_mixed')


def test_comm_list_expanded_is_raw_passthrough_unaffected_by_color_changes():
    """EXPANDED set_type members are never marker-parsed -- regression guard
    that adding the color branch didn't touch this path."""
    result = _render_comm_list({
        'EXP_SET': {'set_type': 'EXPANDED', 'match_action': 'ANY',
                    'community_member': ['color 00:100', '_65000:1_']},
    })
    assert result == _load_fixture('comm_list_expanded_passthrough')


def test_route_map_field_at_key_regression_set_community_inline():
    """Direct regression test for the field@ / .split(',') bug: a plain-list
    'set_community_inline' value (the shape sonic-cfggen -d actually produces)
    must render, not silently vanish."""
    result = _render_route_map({
        ('POLICY', '10'): {
            'route_operation': 'permit',
            'set_community_inline': ['65000:1'],
        }
    })
    assert 'set community 65000:1' in result


def test_route_map_field_at_key_regression_set_large_community_inline():
    result = _render_route_map({
        ('POLICY', '10'): {
            'route_operation': 'permit',
            'set_large_community_inline': ['65000:1:1'],
        }
    })
    assert 'set large-community 65000:1:1' in result


def test_route_map_set_ext_community_delete_only():
    result = _render_route_map({
        ('POLICY', '10'): {
            'route_operation': 'permit',
            'set_ext_community_delete': 'OLD_SET',
        }
    })
    assert 'set extended-comm-list OLD_SET delete' in result
