#!/usr/bin/env python3
import argparse
import ast
import gzip
import html
import re
import string
import tarfile
import zipfile
from pathlib import Path

UPSTREAM_KEYLAYOUT = (
    "./Library/Keyboard Layouts/Programmer Dvorak.bundle/Contents/Resources/" "Programmer Dvorak.keylayout"
)

ACTION_PREFIX = "xkb_"

KEYSYM_TO_CHAR = {
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

KEYSYM_TO_CHAR.update({digit: digit for digit in string.digits})
for codepoint in range(ord("A"), ord("Z") + 1):
    character = chr(codepoint)
    KEYSYM_TO_CHAR[character] = character
for codepoint in range(ord("a"), ord("z") + 1):
    character = chr(codepoint)
    KEYSYM_TO_CHAR[character] = character


def xkb_action_id(character) -> str:
    return f"{ACTION_PREFIX}{ord(character):04x}"


def state_id(sequence) -> str:
    return f"{ACTION_PREFIX}s_{'_'.join(f'{ord(character):04x}' for character in sequence)}"


def xml_escape(value):
    return html.escape(value, quote=True)


def xml_unescape(value):
    return html.unescape(value)


def extract_from_cpio(archive, wanted_name):
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


def extract_upstream_keylayout(package_zip):
    with zipfile.ZipFile(package_zip) as package:
        archive_name = next(name for name in package.namelist() if name.endswith("/Contents/Archive.pax.gz"))
        archive_bytes = package.read(archive_name)

    return extract_from_cpio(gzip.decompress(archive_bytes), UPSTREAM_KEYLAYOUT).decode("utf-8")


def extract_compose_source(libx11_source):
    with tarfile.open(libx11_source, mode="r:*") as archive:
        compose_name = next(name for name in archive.getnames() if name.endswith("/nls/en_US.UTF-8/Compose.pre"))
        return archive.extractfile(compose_name).read().decode("utf-8")


TOKEN_RE = re.compile(r"<([^>]+)>")
OUTPUT_RE = re.compile(r':\s*"((?:\\.|[^"\\])*)"')


def unescape_compose_string(value):
    return ast.literal_eval(f'"{value}"')


def parse_compose(compose_source):
    sequences = []
    for raw_line in compose_source.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line.startswith("<Multi_key>"):
            continue

        output_match = OUTPUT_RE.search(line)
        if output_match is None:
            continue

        tokens = TOKEN_RE.findall(line.split(":", 1)[0])
        if not tokens or tokens[0] != "Multi_key":
            continue

        chars = []
        for token in tokens[1:]:
            if token.startswith("U") and len(token) >= 5:
                try:
                    chars.append(chr(int(token[1:], 16)))
                    continue
                except ValueError:
                    pass
            char = KEYSYM_TO_CHAR.get(token)
            if char is None:
                break
            chars.append(char)
        else:
            sequences.append((tuple(chars), unescape_compose_string(output_match.group(1))))

    return sequences


ACTION_BLOCK_RE = re.compile(r"\n\t<action id=\"([^\"]+)\">.*?\n\t</action>", re.DOTALL)
NONE_OUTPUT_RE = re.compile(r"<when\s+state=\"none\"\s+output=\"([^\"]*)\"")
KEY_OUTPUT_RE = re.compile(r"(<key\b[^>\n]*?)\soutput=\"([^\"]*)\"([^>\n]*/>)")


def parse_original_actions(keylayout):
    actions = {}
    for match in ACTION_BLOCK_RE.finditer(keylayout):
        actions[match.group(1)] = match.group(0)
    return actions


def discover_action_names(keylayout, original_actions):
    action_names = {}
    for action_id, block in original_actions.items():
        match = NONE_OUTPUT_RE.search(block)
        if match is None:
            continue
        value = xml_unescape(match.group(1))
        if len(value) == 1 and value.isprintable():
            action_names.setdefault(value, action_id)

    for match in KEY_OUTPUT_RE.finditer(keylayout):
        value = xml_unescape(match.group(2))
        if len(value) == 1 and value.isprintable():
            action_names.setdefault(value, xkb_action_id(value))

    return action_names


def promote_printable_keys(keylayout, action_names):
    def replace(match):
        value = xml_unescape(match.group(2))
        action_id = action_names.get(value)
        if action_id is None:
            return match.group(0)
        return f'{match.group(1)} action="{action_id}"{match.group(3)}'

    return KEY_OUTPUT_RE.sub(replace, keylayout)


def filter_representable_sequences(sequences, action_names):
    representable = {}
    for sequence, output in sequences:
        if sequence and all(character in action_names for character in sequence):
            representable.setdefault(sequence, output)
    return representable


def build_trie(sequences):
    trie = {"children": {}, "output": None}
    for sequence, output in sequences.items():
        node = trie
        for character in sequence:
            node = node["children"].setdefault(character, {"children": {}, "output": None})
        node["output"] = output
    return trie


def node_at(trie, prefix):
    node = trie
    for character in prefix:
        node = node["children"][character]
    return node


def collect_prefixes(trie, prefix=()):
    prefixes = []
    for character, child in trie["children"].items():
        child_prefix = (*prefix, character)
        prefixes.append(child_prefix)
        prefixes.extend(collect_prefixes(child, child_prefix))
    return prefixes


def when_line(state, output=None, next_state=None) -> str:
    if next_state is not None:
        return f'\t  <when state="{state}" next="{next_state}" />'
    return f'\t  <when state="{state}" output="{xml_escape(output)}" />'


def original_none_line(action_id, character, original_actions):
    block = original_actions.get(action_id)
    if block is not None:
        match = re.search(r"\n\t  <when\s+state=\"none\".*?/>", block)
        if match is not None:
            return match.group(0).strip()
    return when_line("none", output=character).strip()


def generate_actions(action_names, original_actions, trie):
    lines = ["  <actions>"]
    lines.extend(
        (
            '\t<action id="compose">',
            '\t  <when state="none" next="compose" />',
            "\t</action>",
        )
    )

    prefixes = collect_prefixes(trie)
    state_for_prefix = {(): "compose", **{prefix: state_id(prefix) for prefix in prefixes}}
    children_by_prefix = {(): trie["children"]}
    for prefix in prefixes:
        children_by_prefix[prefix] = node_at(trie, prefix)["children"]

    char_by_action = {}
    for character, action_id in action_names.items():
        char_by_action.setdefault(action_id, character)

    for action_id in sorted(char_by_action):
        character = char_by_action[action_id]
        lines.extend(
            (
                f'\t<action id="{action_id}">',
                f"\t  {original_none_line(action_id, character, original_actions)}",
            )
        )
        for prefix, children in sorted(children_by_prefix.items()):
            child = children.get(character)
            if child is None:
                continue

            child_prefix = (*prefix, character)
            if child["children"]:
                lines.append(when_line(state_for_prefix[prefix], next_state=state_for_prefix[child_prefix]))
            else:
                lines.append(when_line(state_for_prefix[prefix], output=child["output"]))
        lines.append("\t</action>")

    used_action_ids = set(char_by_action) | {"compose"}
    lines.extend(
        original_actions[action_id].lstrip("\n")
        for action_id in sorted(original_actions)
        if action_id not in used_action_ids
    )

    lines.append("  </actions>")
    return "\n".join(lines)


def generate_terminators(trie):
    lines = ["  <terminators>", '\t<when state="compose" output="" />']
    for prefix in sorted(collect_prefixes(trie)):
        output = node_at(trie, prefix)["output"]
        if output is not None:
            lines.append(f'\t<when state="{state_id(prefix)}" output="{xml_escape(output)}" />')
    lines.append("  </terminators>")
    return "\n".join(lines)


def replace_generated_sections(keylayout, actions, terminators):
    keylayout = re.sub(r"  <actions>.*?  </actions>", actions, keylayout, flags=re.DOTALL)
    return re.sub(r"  <terminators>.*?  </terminators>", terminators, keylayout, flags=re.DOTALL)


def utf16_units(value):
    return len(value.encode("utf-16-le")) // 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--programmer-dvorak-pkg", required=True, type=Path)
    parser.add_argument("--libx11-src", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    keylayout = extract_upstream_keylayout(args.programmer_dvorak_pkg)
    original_actions = parse_original_actions(keylayout)
    action_names = discover_action_names(keylayout, original_actions)

    compose_source = extract_compose_source(args.libx11_src)
    sequences = filter_representable_sequences(parse_compose(compose_source), action_names)
    trie = build_trie(sequences)

    keylayout = promote_printable_keys(keylayout, action_names)
    keylayout = re.sub(
        r'<keyboard group="0" id="[^"]+" name="[^"]+" maxout="[^"]+">',
        (
            '<keyboard group="0" id="6455" name="Programmer Dvorak Compose" '
            f'maxout="{max([1, *(utf16_units(output) for output in sequences.values())])}">'
        ),
        keylayout,
        count=1,
    )
    keylayout = replace_generated_sections(
        keylayout,
        generate_actions(action_names, original_actions, trie),
        generate_terminators(trie),
    )

    args.output.write_text(keylayout, encoding="utf-8")


if __name__ == "__main__":
    main()
