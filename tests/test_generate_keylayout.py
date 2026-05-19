"""Tests for the macOS keylayout generator."""
# ruff: noqa: S314, S405

from __future__ import annotations

import html
import xml.etree.ElementTree as ET

from scripts import generate_keylayout

BASE_LAYOUT = """<?xml version="1.0" encoding="UTF-8"?>
<keyboard group="0" id="1" name="Base" maxout="1">
  <keyMapSet id="ANSI">
    <keyMap index="0">
      <key code="1" output="-" />
      <key code="2" output="=" />
      <key code="3" output="&lt;" />
      <key code="4" output="&gt;" />
      <key code="5" output="." />
      <key code="6" output="L" />
      <key code="7" output="A" />
      <key code="8" output="p" />
      <key code="9" output="o" />
      <key code="10" output="&amp;" />
      <key code="11" output="&quot;" />
      <key code="12" output="P" />
    </keyMap>
  </keyMapSet>
  <actions>
\t<action id="compose">
\t  <when state="none" next="compose" />
\t</action>
\t<action id="dash">
\t  <when state="none" output="-" />
\t  <when state="compose" next="macron" />
\t  <when state="dot" output="&#xB7;" />
\t</action>
\t<action id="doubleacute">
\t  <when state="none" output="=" />
\t  <when state="compose" next="doubleacute" />
\t</action>
\t<action id="less">
\t  <when state="none" output="&#x3C;" />
\t  <when state="compose" next="less" />
\t</action>
\t<action id="greater">
\t  <when state="none" output=">" />
\t  <when state="compose" next="greater" />
\t</action>
\t<action id="period">
\t  <when state="none" output="." />
\t  <when state="compose" next="dot" />
\t  <when state="dot" output="&#x2026;" />
\t</action>
\t<action id="L">
\t  <when state="none" output="L" />
\t</action>
\t<action id="A">
\t  <when state="none" output="A" />
\t</action>
\t<action id="p">
\t  <when state="none" output="p" />
\t</action>
\t<action id="o">
\t  <when state="none" output="o" />
\t</action>
\t<action id="P">
\t  <when state="none" output="P" />
\t</action>
  </actions>
  <terminators>
\t<when state="compose" output="" />
\t<when state="macron" output="-" />
\t<when state="doubleacute" output="=" />
\t<when state="dot" output="." />
  </terminators>
</keyboard>
"""

SEQUENCES: dict[generate_keylayout.ComposeSequence, str] = {
    ("L", "L", "A", "P"): "🖖",
    ("p", "o", "o"): "💩",
    ("-", "-", "-"): "—",
    ("-", ">"): "→",
    ("<", "-"): "←",
    ("=", ">"): "⇒",
    ("<", "="): "≤",
    (">", "="): "≥",
    (".", "."): "…",
    ("&", ">"): "&",
    ('"', ">"): '"',
    ("<", "<"): "<",
    (">", ">"): ">",
}


def generated_layout() -> str:
    """Return a generated layout from the small test fixture."""
    original_actions = generate_keylayout.parse_original_actions(BASE_LAYOUT)
    action_names = generate_keylayout.discover_action_names(BASE_LAYOUT, original_actions)
    trie = generate_keylayout.build_trie(SEQUENCES)

    keylayout = generate_keylayout.promote_printable_keys(BASE_LAYOUT, action_names)
    keylayout = generate_keylayout.insert_generated_passthrough_actions(
        keylayout,
        generate_keylayout.generated_passthrough_characters(action_names, original_actions),
    )
    return generate_keylayout.inject_generated_transitions(
        keylayout,
        generate_keylayout.generate_transition_additions(action_names, trie),
    )


def action_ids(root: ET.Element) -> set[str]:
    """Return all action IDs in an ElementTree layout."""
    return {action.attrib["id"] for action in root.findall(".//action")}


def key_action_refs(root: ET.Element) -> list[str]:
    """Return key action references in an ElementTree layout."""
    return [key.attrib["action"] for key in root.findall(".//key") if "action" in key.attrib]


def action_for_key_code(root: ET.Element, code: str) -> str:
    """Return the action ID used by a key code."""
    key = root.find(f'.//key[@code="{code}"]')
    assert key is not None, f"missing key code {code}"
    return key.attrib["action"]


def action_when_by_state(root: ET.Element) -> dict[str, dict[str, ET.Element]]:
    """Return action when elements keyed by action ID and state."""
    result: dict[str, dict[str, ET.Element]] = {}
    for action in root.findall(".//action"):
        result[action.attrib["id"]] = {when.attrib["state"]: when for when in action.findall("when")}
    return result


def assert_compose_output(root: ET.Element, sequence: tuple[str, ...], output: str) -> None:
    """Assert that a compose sequence follows generated transitions to an output."""
    key_actions = {
        "L": action_for_key_code(root, "6"),
        "A": action_for_key_code(root, "7"),
        "p": action_for_key_code(root, "8"),
        "o": action_for_key_code(root, "9"),
        "P": action_for_key_code(root, "12"),
        "-": action_for_key_code(root, "1"),
        "=": action_for_key_code(root, "2"),
        "<": action_for_key_code(root, "3"),
        ">": action_for_key_code(root, "4"),
        ".": action_for_key_code(root, "5"),
    }
    whens = action_when_by_state(root)
    state = "compose"
    actual_output: str | None = None
    for character in sequence:
        when = whens[key_actions[character]][state]
        if "output" in when.attrib:
            assert character == sequence[-1]
            actual_output = when.attrib["output"]
            break
        state = when.attrib["next"]

    assert actual_output == output, f"sequence {sequence!r}"


def test_generated_fixture_is_parseable_xml() -> None:
    """Generated fixture output is valid XML when the fixture contains no control references."""
    ET.fromstring(generated_layout())


def test_key_actions_resolve_and_actions_are_not_empty() -> None:
    """All key action references resolve and every action has behavior."""
    root = ET.fromstring(generated_layout())
    ids = action_ids(root)

    assert set(key_action_refs(root)) <= ids
    assert all(action.findall("when") for action in root.findall(".//action"))


def test_no_action_has_duplicate_state_branches() -> None:
    """Generated additions do not leave duplicate state branches in one action."""
    root = ET.fromstring(generated_layout())

    for action in root.findall(".//action"):
        states = [when.attrib["state"] for when in action.findall("when")]
        assert len(states) == len(set(states)), action.attrib["id"]


def test_original_actions_are_preferred_for_promoted_keys_and_roots() -> None:
    """Dash and equals keep their original physical-key actions for generated roots."""
    root = ET.fromstring(generated_layout())
    whens = action_when_by_state(root)

    assert action_for_key_code(root, "1") == "dash"
    assert action_for_key_code(root, "2") == "doubleacute"
    assert whens["dash"]["compose"].attrib["next"] == generate_keylayout.state_id(("-",))
    assert whens["doubleacute"]["compose"].attrib["next"] == generate_keylayout.state_id(("=",))


def test_representative_generated_paths_exist() -> None:
    """Representative XKB compose paths are present in the generated graph."""
    root = ET.fromstring(generated_layout())

    for sequence, output in {
        ("L", "L", "A", "P"): "🖖",
        ("p", "o", "o"): "💩",
        ("-", "-", "-"): "—",
        ("-", ">"): "→",
        ("<", "-"): "←",
        ("=", ">"): "⇒",
        ("<", "="): "≤",
        (">", "="): "≥",
        (".", "."): "…",
    }.items():
        assert_compose_output(root, sequence, output)


def test_generated_xml_sensitive_outputs_use_numeric_escapes() -> None:
    """XML-sensitive generated output attributes use numeric escapes."""
    layout = generated_layout()

    assert 'output="&#x26;"' in layout
    assert 'output="&#x22;"' in layout
    assert 'output="&#x3C;"' in layout
    assert 'output="&#x3E;"' in layout
    assert 'output="&amp;"' not in layout
    assert 'output="&quot;"' not in layout
    assert html.unescape("&#x26;&#x22;&#x3C;&#x3E;") == '&"<>'
