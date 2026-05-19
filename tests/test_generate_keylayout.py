"""Tests for the macOS keylayout generator."""

import html
from typing import Protocol, cast

import pytest
from defusedxml import ElementTree

from scripts import generate_keylayout

_BASE_LAYOUT = """<?xml version="1.0" encoding="UTF-8"?>
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
  <action id="compose">
    <when state="none" next="compose" />
  </action>
  <action id="dash">
    <when state="none" output="-" />
    <when state="compose" next="macron" />
    <when state="dot" output="&#xB7;" />
  </action>
  <action id="doubleacute">
    <when state="none" output="=" />
    <when state="compose" next="doubleacute" />
  </action>
  <action id="less">
    <when state="none" output="&#x3C;" />
    <when state="compose" next="less" />
  </action>
  <action id="greater">
    <when state="none" output=">" />
    <when state="compose" next="greater" />
  </action>
  <action id="period">
    <when state="none" output="." />
    <when state="compose" next="dot" />
    <when state="dot" output="&#x2026;" />
  </action>
  <action id="L">
    <when state="none" output="L" />
  </action>
  <action id="A">
    <when state="none" output="A" />
  </action>
  <action id="p">
    <when state="none" output="p" />
  </action>
  <action id="o">
    <when state="none" output="o" />
  </action>
  <action id="P">
    <when state="none" output="P" />
  </action>
  </actions>
  <terminators>
  <when state="compose" output="" />
  <when state="macron" output="-" />
  <when state="doubleacute" output="=" />
  <when state="dot" output="." />
  </terminators>
</keyboard>
"""

_SEQUENCES: dict[generate_keylayout.ComposeSequence, str] = {
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


class _XmlElement(Protocol):
    """Minimal ElementTree element protocol used by the tests."""

    attrib: dict[str, str]

    def find(self, path: str) -> _XmlElement | None:
        """Return the first matching child element."""
        ...

    def findall(self, path: str) -> list[_XmlElement]:
        """Return all matching child elements."""
        ...


@pytest.fixture(scope="session")
def generated_root() -> _XmlElement:
    """Return the parsed generated fixture layout."""
    return _parse_layout(_generated_layout())


def test_generated_fixture_is_parseable_xml(generated_root: _XmlElement) -> None:
    """Generated fixture output is valid XML when the fixture contains no control references."""
    assert generated_root.attrib["name"] == "Base"


def test_key_actions_resolve_and_actions_are_not_empty(generated_root: _XmlElement) -> None:
    """All key action references resolve and every action has behavior."""
    ids = _action_ids(generated_root)

    assert set(_key_action_refs(generated_root)) <= ids
    assert all(action.findall("when") for action in generated_root.findall(".//action"))


def test_no_action_has_duplicate_state_branches(generated_root: _XmlElement) -> None:
    """Generated additions do not leave duplicate state branches in one action."""
    for action in generated_root.findall(".//action"):
        states = [when.attrib["state"] for when in action.findall("when")]
        assert len(states) == len(set(states)), action.attrib["id"]


def test_original_actions_are_preferred_for_promoted_keys_and_roots(generated_root: _XmlElement) -> None:
    """Dash and equals keep their original physical-key actions for generated roots."""
    whens = _action_when_by_state(generated_root)

    assert _action_for_key_code(generated_root, "1") == "dash"
    assert _action_for_key_code(generated_root, "2") == "doubleacute"
    assert whens["dash"]["compose"].attrib["next"] == generate_keylayout.state_id(("-",))
    assert whens["doubleacute"]["compose"].attrib["next"] == generate_keylayout.state_id(("=",))


@pytest.mark.parametrize(
    ("sequence", "output"),
    [
        (("L", "L", "A", "P"), "🖖"),
        (("p", "o", "o"), "💩"),
        (("-", "-", "-"), "—"),
        (("-", ">"), "→"),
        (("<", "-"), "←"),
        (("=", ">"), "⇒"),
        (("<", "="), "≤"),
        ((">", "="), "≥"),
        ((".", "."), "…"),
    ],
)
def test_representative_generated_paths_exist(
    generated_root: _XmlElement,
    sequence: tuple[str, ...],
    output: str,
) -> None:
    """Representative XKB compose paths are present in the generated graph."""
    _assert_compose_output(generated_root, sequence, output)


def test_generated_xml_sensitive_outputs_use_numeric_escapes() -> None:
    """XML-sensitive generated output attributes use numeric escapes."""
    layout = _generated_layout()

    assert 'output="&#x26;"' in layout
    assert 'output="&#x22;"' in layout
    assert 'output="&#x3C;"' in layout
    assert 'output="&#x3E;"' in layout
    assert 'output="&amp;"' not in layout
    assert 'output="&quot;"' not in layout
    assert html.unescape("&#x26;&#x22;&#x3C;&#x3E;") == '&"<>'


def _generated_layout() -> str:
    """Return a generated layout from the small test fixture."""
    original_actions = generate_keylayout.parse_original_actions(_BASE_LAYOUT)
    action_names = generate_keylayout.discover_action_names(_BASE_LAYOUT, original_actions)
    trie = generate_keylayout.build_trie(_SEQUENCES)

    keylayout = generate_keylayout.promote_printable_keys(_BASE_LAYOUT, action_names)
    keylayout = generate_keylayout.insert_generated_passthrough_actions(
        keylayout,
        generate_keylayout.generated_passthrough_characters(action_names, original_actions),
    )
    return generate_keylayout.inject_generated_transitions(
        keylayout,
        generate_keylayout.generate_transition_additions(action_names, trie),
    )


def _parse_layout(layout: str) -> _XmlElement:
    """Parse a keylayout XML snippet with entity expansion protections.

    Returns:
        The parsed root XML element.
    """
    return cast("_XmlElement", ElementTree.fromstring(layout))


def _action_ids(root: _XmlElement) -> set[str]:
    """Return all action IDs in an ElementTree layout."""
    return {action.attrib["id"] for action in root.findall(".//action")}


def _key_action_refs(root: _XmlElement) -> list[str]:
    """Return key action references in an ElementTree layout."""
    return [key.attrib["action"] for key in root.findall(".//key") if "action" in key.attrib]


def _action_for_key_code(root: _XmlElement, code: str) -> str:
    """Return the action ID used by a key code."""
    key = root.find(f'.//key[@code="{code}"]')
    assert key is not None, f"missing key code {code}"
    return key.attrib["action"]


def _action_when_by_state(root: _XmlElement) -> dict[str, dict[str, _XmlElement]]:
    """Return action when elements keyed by action ID and state."""
    result: dict[str, dict[str, _XmlElement]] = {}
    for action in root.findall(".//action"):
        result[action.attrib["id"]] = {when.attrib["state"]: when for when in action.findall("when")}
    return result


def _assert_compose_output(root: _XmlElement, sequence: tuple[str, ...], output: str) -> None:
    """Assert that a compose sequence follows generated transitions to an output."""
    key_actions = {
        "L": _action_for_key_code(root, "6"),
        "A": _action_for_key_code(root, "7"),
        "p": _action_for_key_code(root, "8"),
        "o": _action_for_key_code(root, "9"),
        "P": _action_for_key_code(root, "12"),
        "-": _action_for_key_code(root, "1"),
        "=": _action_for_key_code(root, "2"),
        "<": _action_for_key_code(root, "3"),
        ">": _action_for_key_code(root, "4"),
        ".": _action_for_key_code(root, "5"),
    }
    whens = _action_when_by_state(root)
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
