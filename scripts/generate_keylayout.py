"""Generate the macOS Programmer Dvorak Compose keylayout."""

import argparse
import ast
import gzip
import html
import re
import string
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping

_UPSTREAM_KEYLAYOUT = (
    "./Library/Keyboard Layouts/Programmer Dvorak.bundle/Contents/Resources/Programmer Dvorak.keylayout"
)

_ACTION_PREFIX = "xkb_"
_INDENT_SPACES_PER_TAB = 2
_UNICODE_KEYSYM_MIN_LENGTH = 5
_TOKEN_RE = re.compile(r"<([^>]+)>")
_OUTPUT_RE = re.compile(r':\s*"((?:\\.|[^"\\])*)"')
_ACTION_BLOCK_RE = re.compile(r"\n\t<action id=\"([^\"]+)\">.*?\n\t</action>", re.DOTALL)
_NONE_OUTPUT_RE = re.compile(r"<when\s+state=\"none\"\s+output=\"([^\"]*)\"")
_KEY_OUTPUT_RE = re.compile(r"(<key\b[^>\n]*?)\soutput=\"([^\"]*)\"([^>\n]*/>)")

_KEYSYM_TO_CHAR = {
    "space": " ",
    "exclam": "!",
    "quotedbl": '"',
    "numbersign": "#",
    "dollar": "$",
    "percent": "%",
    "ampersand": "&",
    "apostrophe": "'",
    "parenleft": "(",
    "parenright": ")",
    "asterisk": "*",
    "plus": "+",
    "comma": ",",
    "minus": "-",
    "period": ".",
    "slash": "/",
    "colon": ":",
    "semicolon": ";",
    "less": "<",
    "equal": "=",
    "greater": ">",
    "question": "?",
    "at": "@",
    "bracketleft": "[",
    "backslash": "\\",
    "bracketright": "]",
    "asciicircum": "^",
    "underscore": "_",
    "grave": "`",
    "quoteleft": "`",
    "braceleft": "{",
    "bar": "|",
    "braceright": "}",
    "asciitilde": "~",
    "nobreakspace": "\u00a0",
    "acute": "\u00b4",
    "diaeresis": "\u00a8",
    "degree": "\u00b0",
    "macron": "\u00af",
    "cedilla": "\u00b8",
    "breve": "\u02d8",
    "abovedot": "\u02d9",
    "caron": "\u02c7",
}

_KEYSYM_TO_CHAR.update({digit: digit for digit in string.digits})
for codepoint in range(ord("A"), ord("Z") + 1):
    character = chr(codepoint)
    _KEYSYM_TO_CHAR[character] = character
for codepoint in range(ord("a"), ord("z") + 1):
    character = chr(codepoint)
    _KEYSYM_TO_CHAR[character] = character


type ComposeSequence = tuple[str, ...]
type ComposeEntry = tuple[ComposeSequence, str]


class _TrieNode(TypedDict):
    children: dict[str, _TrieNode]
    output: str | None


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--programmer-dvorak-pkg", required=True, type=Path)
    parser.add_argument("--libx11-src", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    keylayout = _extract_upstream_keylayout(args.programmer_dvorak_pkg)
    original_actions = _parse_original_actions(keylayout)
    action_names = _discover_action_names(keylayout, original_actions)

    compose_source = _extract_compose_source(args.libx11_src)
    sequences = _filter_representable_sequences(_parse_compose(compose_source), action_names)
    trie = _build_trie(sequences)

    keylayout = _promote_printable_keys(keylayout, action_names)
    keylayout = re.sub(
        r'<keyboard group="0" id="[^"]+" name="[^"]+" maxout="[^"]+">',
        (
            '<keyboard group="0" id="6455" name="Programmer Dvorak Compose" '
            f'maxout="{max([1, *(_utf16_units(output) for output in sequences.values())])}">'
        ),
        keylayout,
        count=1,
    )
    keylayout = _replace_generated_sections(
        keylayout,
        _generate_actions(action_names, original_actions, trie),
        _generate_terminators(trie),
    )

    args.output.write_text(_normalize_leading_indentation(keylayout), encoding="utf-8")


def _xkb_action_id(character: str) -> str:
    return f"{_ACTION_PREFIX}{ord(character):04x}"


def _state_id(sequence: Iterable[str]) -> str:
    return f"{_ACTION_PREFIX}s_{'_'.join(f'{ord(character):04x}' for character in sequence)}"


def _xml_escape(value: str) -> str:
    return html.escape(value, quote=True)


def _xml_unescape(value: str) -> str:
    return html.unescape(value)


def _normalize_leading_indentation(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        content = line.lstrip(" \t")
        leading = line[: len(line) - len(content)]
        if not leading:
            lines.append(line)
            continue

        spaces = leading.count(" ")
        tabs = leading.count("\t")
        indent = tabs + (spaces + _INDENT_SPACES_PER_TAB - 1) // _INDENT_SPACES_PER_TAB
        lines.append(f"{'\t' * indent}{content}")
    return "".join(lines)


def _extract_from_cpio(archive: bytes, wanted_name: str) -> bytes:
    offset = 0
    while offset + 76 <= len(archive):
        header = archive[offset : offset + 76]
        offset += 76
        if header[:6] != b"070707":
            msg = "unsupported cpio archive format"
            raise ValueError(msg)

        name_size = int(header[59:65], 8)
        file_size = int(header[65:76], 8)
        name = archive[offset : offset + name_size].rstrip(b"\0").decode("utf-8")
        offset += name_size

        data = archive[offset : offset + file_size]
        offset += file_size

        if name == "TRAILER!!!":
            break
        if name == wanted_name:
            return data

    raise FileNotFoundError(wanted_name)


def _extract_upstream_keylayout(package_zip: Path) -> str:
    with zipfile.ZipFile(package_zip) as package:
        archive_name = next(name for name in package.namelist() if name.endswith("/Contents/Archive.pax.gz"))
        archive_bytes = package.read(archive_name)

    return _extract_from_cpio(gzip.decompress(archive_bytes), _UPSTREAM_KEYLAYOUT).decode("utf-8")


def _extract_compose_source(libx11_source: Path) -> str:
    with tarfile.open(libx11_source, mode="r:*") as archive:
        compose_name = next(name for name in archive.getnames() if name.endswith("/nls/en_US.UTF-8/Compose.pre"))
        if (compose_file := archive.extractfile(compose_name)) is None:
            raise FileNotFoundError(compose_name)
        return compose_file.read().decode("utf-8")


def _unescape_compose_string(value: str) -> str:
    return ast.literal_eval(f'"{value}"')


def _strip_compose_comment(raw_line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(raw_line):
        if escaped:
            escaped = False
            continue
        if quote is not None:
            if character == "\\":
                escaped = True
                continue
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
            continue
        if character == "#":
            return raw_line[:index].strip()
    return raw_line.strip()


def _parse_compose(compose_source: str) -> list[ComposeEntry]:
    sequences: list[ComposeEntry] = []
    for raw_line in compose_source.splitlines():
        line = _strip_compose_comment(raw_line)
        if not line.startswith("<Multi_key>"):
            continue

        if (output_match := _OUTPUT_RE.search(line)) is None:
            continue

        tokens = _TOKEN_RE.findall(line.split(":", 1)[0])
        if not tokens or tokens[0] != "Multi_key":
            continue

        chars: list[str] = []
        for token in tokens[1:]:
            if token.startswith("U") and len(token) >= _UNICODE_KEYSYM_MIN_LENGTH:
                try:
                    chars.append(chr(int(token[1:], 16)))
                    continue
                except ValueError:
                    pass
            if (char := _KEYSYM_TO_CHAR.get(token)) is None:
                break
            chars.append(char)
        else:
            sequences.append((tuple(chars), _unescape_compose_string(output_match.group(1))))

    return sequences


def _parse_original_actions(keylayout: str) -> dict[str, str]:
    actions: dict[str, str] = {}
    for match in _ACTION_BLOCK_RE.finditer(keylayout):
        actions[match.group(1)] = match.group(0)
    return actions


def _discover_action_names(keylayout: str, original_actions: Mapping[str, str]) -> dict[str, str]:
    action_names: dict[str, str] = {}
    for action_id, block in original_actions.items():
        if (match := _NONE_OUTPUT_RE.search(block)) is None:
            continue
        value = _xml_unescape(match.group(1))
        if len(value) == 1 and value.isprintable():
            action_names.setdefault(value, action_id)

    for match in _KEY_OUTPUT_RE.finditer(keylayout):
        value = _xml_unescape(match.group(2))
        if len(value) == 1 and value.isprintable():
            action_names.setdefault(value, _xkb_action_id(value))

    return action_names


def _promote_printable_keys(keylayout: str, action_names: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = _xml_unescape(match.group(2))
        if (action_id := action_names.get(value)) is None:
            return match.group(0)
        return f'{match.group(1)} action="{action_id}"{match.group(3)}'

    return _KEY_OUTPUT_RE.sub(replace, keylayout)


def _filter_representable_sequences(
    sequences: Iterable[ComposeEntry],
    action_names: Collection[str],
) -> dict[ComposeSequence, str]:
    representable: dict[ComposeSequence, str] = {}
    for sequence, output in sequences:
        if sequence and all(character in action_names for character in sequence):
            representable.setdefault(sequence, output)
    return representable


def _build_trie(sequences: Mapping[ComposeSequence, str]) -> _TrieNode:
    trie: _TrieNode = {"children": {}, "output": None}
    for sequence, output in sequences.items():
        node = trie
        for character in sequence:
            node = node["children"].setdefault(character, {"children": {}, "output": None})
        node["output"] = output
    return trie


def _node_at(trie: _TrieNode, prefix: Iterable[str]) -> _TrieNode:
    node = trie
    for character in prefix:
        node = node["children"][character]
    return node


def _collect_prefixes(trie: _TrieNode, prefix: ComposeSequence = ()) -> list[ComposeSequence]:
    prefixes: list[ComposeSequence] = []
    for character, child in trie["children"].items():
        child_prefix = (*prefix, character)
        prefixes.append(child_prefix)
        prefixes.extend(_collect_prefixes(child, child_prefix))
    return prefixes


def _when_line(state: str, output: str | None = None, next_state: str | None = None) -> str:
    if next_state is not None:
        return f'\t  <when state="{state}" next="{next_state}" />'
    if output is None:
        msg = "output is required when next_state is not set"
        raise ValueError(msg)
    return f'\t  <when state="{state}" output="{_xml_escape(output)}" />'


def _original_none_line(action_id: str, character: str, original_actions: Mapping[str, str]) -> str:
    block = original_actions.get(action_id)
    if block is not None:
        match = re.search(r"\n\t  <when\s+state=\"none\".*?/>", block)
        if match is not None:
            return match.group(0).strip()
    return _when_line("none", output=character).strip()


def _generate_actions(
    action_names: Mapping[str, str],
    original_actions: Mapping[str, str],
    trie: _TrieNode,
) -> str:
    lines = ["  <actions>"]
    lines.extend(
        (
            '\t<action id="compose">',
            '\t  <when state="none" next="compose" />',
            "\t</action>",
        ),
    )

    prefixes = _collect_prefixes(trie)
    state_for_prefix = {(): "compose", **{prefix: _state_id(prefix) for prefix in prefixes}}
    children_by_prefix: dict[ComposeSequence, dict[str, _TrieNode]] = {(): trie["children"]}
    for prefix in prefixes:
        children_by_prefix[prefix] = _node_at(trie, prefix)["children"]

    char_by_action: dict[str, str] = {}
    for character, action_id in action_names.items():
        char_by_action.setdefault(action_id, character)

    for action_id in sorted(char_by_action):
        character = char_by_action[action_id]
        lines.extend(
            (
                f'\t<action id="{action_id}">',
                f"\t  {_original_none_line(action_id, character, original_actions)}",
            ),
        )
        for prefix, children in sorted(children_by_prefix.items()):
            if (child := children.get(character)) is None:
                continue

            child_prefix = (*prefix, character)
            if child["children"]:
                lines.append(_when_line(state_for_prefix[prefix], next_state=state_for_prefix[child_prefix]))
            else:
                lines.append(_when_line(state_for_prefix[prefix], output=child["output"]))
        lines.append("\t</action>")

    used_action_ids = set(char_by_action) | {"compose"}
    lines.extend(
        original_actions[action_id].lstrip("\n")
        for action_id in sorted(original_actions)
        if action_id not in used_action_ids
    )

    lines.append("  </actions>")
    return "\n".join(lines)


def _generate_terminators(trie: _TrieNode) -> str:
    lines = ["  <terminators>", '\t<when state="compose" output="" />']
    for prefix in sorted(_collect_prefixes(trie)):
        output = _node_at(trie, prefix)["output"]
        if output is not None:
            lines.append(f'\t<when state="{_state_id(prefix)}" output="{_xml_escape(output)}" />')
    lines.append("  </terminators>")
    return "\n".join(lines)


def _replace_generated_sections(keylayout: str, actions: str, terminators: str) -> str:
    keylayout = re.sub(r"  <actions>.*?  </actions>", actions, keylayout, flags=re.DOTALL)
    return re.sub(r"  <terminators>.*?  </terminators>", terminators, keylayout, flags=re.DOTALL)


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


if __name__ == "__main__":
    _main()
