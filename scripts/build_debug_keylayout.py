#!/usr/bin/env python3
"""Build debug variants of the macOS keylayout."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


KEY_OUTPUT_RE = re.compile(r'(<key\b[^>\n]*?)\soutput="([^"]*)"([^>\n]*/>)')
KEY_ACTION_RE = re.compile(r'(<key\b[^>\n]*?)\saction="([^"]*)"([^>\n]*/>)')
ACTION_BLOCK_RE = re.compile(r'\n\t<action id="([^"]+)">(.*?)\n\t</action>', re.DOTALL)
WHEN_RE = re.compile(r"<when\b(.*?)/>")
ATTR_RE = re.compile(r'\b(state|next|output)="([^"]*)"')
TERMINATORS_RE = re.compile(r"\n  <terminators>.*?\n  </terminators>", re.DOTALL)


def xkb_action_id(character: str) -> str:
    return f"xkb_{ord(character):04x}"


def xml_escape(value: str) -> str:
    replacements = {
        "&": "&#x26;",
        '"': "&#x22;",
        "<": "&#x3C;",
        ">": "&#x3E;",
    }
    return "".join(replacements.get(character, character) for character in value)


def attrs(raw: str) -> dict[str, str]:
    return {key: value for key, value in ATTR_RE.findall(raw)}


def state_prefix(state: str) -> tuple[str, ...] | None:
    if not state.startswith("xkb_s_"):
        return None
    return tuple(state.removeprefix("xkb_s_").split("_"))


def prefix_state(prefix: tuple[str, ...]) -> str:
    return "xkb_s_" + "_".join(prefix)


def build_promotion_only(source: str) -> str:
    added: dict[str, str] = {}

    def replace_key(match: re.Match[str]) -> str:
        prefix, raw_output, suffix = match.groups()
        output = html.unescape(raw_output)
        if len(output) != 1 or not output.isprintable():
            return match.group(0)

        action_id = xkb_action_id(output)
        added.setdefault(action_id, output)
        return f'{prefix} action="{action_id}"{suffix}'

    promoted = KEY_OUTPUT_RE.sub(replace_key, source)
    action_blocks = [
        "\t<action id=\"{action_id}\">\n"
        "\t  <when state=\"none\" output=\"{output}\" />\n"
        "\t</action>".format(action_id=action_id, output=xml_escape(output))
        for action_id, output in sorted(added.items())
    ]
    return re.sub(r"\n  </actions>", "\n" + "\n".join(action_blocks) + "\n  </actions>", promoted, count=1)


def action_characters(layout: str) -> dict[str, str]:
    terminators = {
        attrs(match.group(1)).get("state"): html.unescape(attrs(match.group(1)).get("output", ""))
        for section in TERMINATORS_RE.findall(layout)
        for match in WHEN_RE.finditer(section)
    }
    characters: dict[str, str] = {}
    for action_id, body in ACTION_BLOCK_RE.findall(layout):
        if (character := action_character(action_id, body)) is not None:
            characters[action_id] = character
            continue
        for match in WHEN_RE.finditer(body):
            parsed = attrs(match.group(1))
            if parsed.get("state") != "none" or "next" not in parsed:
                continue
            output = terminators.get(parsed["next"])
            if output is not None and len(output) == 1:
                characters[action_id] = output
                break
    return characters


def ensure_xkb_actions(layout: str, characters: set[str]) -> str:
    existing = set(re.findall(r'<action id="([^"]+)"', layout))
    action_blocks = [
        "\t<action id=\"{action_id}\">\n"
        "\t  <when state=\"none\" output=\"{output}\" />\n"
        "\t</action>".format(action_id=xkb_action_id(character), output=xml_escape(character))
        for character in sorted(characters)
        if xkb_action_id(character) not in existing
    ]
    if not action_blocks:
        return layout
    return re.sub(r"\n  </actions>", "\n" + "\n".join(action_blocks) + "\n  </actions>", layout, count=1)


def rewrite_key_actions_to_xkb(layout: str) -> str:
    characters = action_characters(layout)

    def replace(match: re.Match[str]) -> str:
        prefix, action_id, suffix = match.groups()
        if action_id == "compose" or action_id.startswith("xkb_"):
            return match.group(0)
        character = characters.get(action_id)
        if character is None:
            return match.group(0)
        return f'{prefix} action="{xkb_action_id(character)}"{suffix}'

    rewritten = KEY_ACTION_RE.sub(replace, layout)
    return ensure_xkb_actions(rewritten, set(characters.values()))


def remove_non_xkb_actions(layout: str) -> str:
    def replace(match: re.Match[str]) -> str:
        action_id = match.group(1)
        if action_id == "compose" or action_id.startswith("xkb_"):
            return match.group(0)
        return ""

    return ACTION_BLOCK_RE.sub(replace, layout)


def terminator_outputs(layout: str) -> dict[str, str]:
    return {
        attrs(match.group(1)).get("state", ""): html.unescape(attrs(match.group(1)).get("output", ""))
        for section in TERMINATORS_RE.findall(layout)
        for match in WHEN_RE.finditer(section)
    }


def strip_original_compose_rules(layout: str) -> str:
    terminators = terminator_outputs(layout)

    def strip_action(match: re.Match[str]) -> str:
        action_id = match.group(1)
        kept_lines: list[str] = []
        for line in match.group(2).splitlines():
            when_match = WHEN_RE.search(line)
            if when_match is None:
                kept_lines.append(line)
                continue
            parsed = attrs(when_match.group(1))
            if action_id == "compose" and parsed.get("state") == "none":
                kept_lines.append(line)
            elif parsed.get("state") == "none" and "output" in parsed:
                kept_lines.append(line)
            elif parsed.get("state") == "none" and "next" in parsed:
                output = terminators.get(parsed["next"])
                if output is not None:
                    kept_lines.append(f'\t  <when state="none" output="{xml_escape(output)}" />')

        body = "\n".join(kept_lines)
        return f'\n\t<action id="{action_id}">{body}\n\t</action>'

    stripped = ACTION_BLOCK_RE.sub(strip_action, layout)
    return TERMINATORS_RE.sub(
        '\n  <terminators>\n\t<when state="compose" output="" />\n  </terminators>',
        stripped,
        count=1,
    )


def strip_original_compose_entry_points(layout: str) -> str:
    terminators = terminator_outputs(layout)

    def strip_action(match: re.Match[str]) -> str:
        action_id = match.group(1)
        kept_lines: list[str] = []
        for line in match.group(2).splitlines():
            when_match = WHEN_RE.search(line)
            if when_match is None:
                kept_lines.append(line)
                continue
            parsed = attrs(when_match.group(1))
            if action_id == "compose" and parsed.get("state") == "none":
                kept_lines.append(line)
            elif parsed.get("state") == "compose":
                continue
            elif parsed.get("state") == "none" and "next" in parsed:
                output = terminators.get(parsed["next"])
                if output is not None:
                    kept_lines.append(f'\t  <when state="none" output="{xml_escape(output)}" />')
            else:
                kept_lines.append(line)

        body = "\n".join(kept_lines)
        return f'\n\t<action id="{action_id}">{body}\n\t</action>'

    return ACTION_BLOCK_RE.sub(strip_action, layout)


def build_xkb_only_base(layout: str) -> str:
    rewritten = rewrite_key_actions_to_xkb(layout)
    stripped = strip_original_compose_rules(rewritten)
    return remove_non_xkb_actions(stripped)


def build_xkb_semantics_base(layout: str) -> str:
    return strip_original_compose_rules(layout)


def build_xkb_semantics_compat_base(layout: str) -> str:
    return strip_original_compose_entry_points(layout)


def action_character(action_id: str, body: str) -> str | None:
    if action_id.startswith("xkb_"):
        try:
            return chr(int(action_id.removeprefix("xkb_"), 16))
        except ValueError:
            return None

    for match in WHEN_RE.finditer(body):
        parsed = attrs(match.group(1))
        if parsed.get("state") != "none" or "output" not in parsed:
            continue
        output = html.unescape(parsed["output"])
        if len(output) == 1:
            return output
    return None


def utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def normalized_when_line(match: re.Match[str]) -> str:
    line = match.group(0)
    parsed = attrs(match.group(1))
    if "output" not in parsed:
        return "\t  " + line
    output = html.unescape(parsed["output"])
    return "\t  " + re.sub(
        r'output="[^"]*"',
        f'output="{xml_escape(output)}"',
        line,
        count=1,
    )


def blocked_root_states(base: str, generated: str) -> set[str]:
    base_actions = dict(ACTION_BLOCK_RE.findall(base))
    blocked: set[str] = set()

    for action_id, body in ACTION_BLOCK_RE.findall(generated):
        base_body = base_actions.get(action_id)
        if base_body is None or 'state="compose"' not in base_body:
            continue
        for match in WHEN_RE.finditer(body):
            parsed = attrs(match.group(1))
            if parsed.get("state") == "compose" and "next" in parsed:
                blocked.add(parsed["next"])

    return blocked


def generated_output_records(
    generated: str,
    blocked_roots: set[str],
    *,
    use_xkb_actions: bool,
    max_utf16_units: int,
) -> list[tuple[str, tuple[str, ...], str]]:
    records: list[tuple[str, tuple[str, ...], str]] = []
    for action_id, body in ACTION_BLOCK_RE.findall(generated):
        character = action_character(action_id, body)
        if character is None:
            continue
        character_hex = f"{ord(character):04x}"
        for match in WHEN_RE.finditer(body):
            parsed = attrs(match.group(1))
            state = parsed.get("state")
            if state is None or state == "none" or "output" not in parsed:
                continue
            if utf16_units(html.unescape(parsed["output"])) > max_utf16_units:
                continue
            if state == "compose":
                sequence: tuple[str, ...] = (character_hex,)
            else:
                prefix = state_prefix(state)
                if prefix is None:
                    continue
                sequence = (*prefix, character_hex)
            if prefix_state(sequence[:1]) in blocked_roots:
                continue
            target_action_id = xkb_action_id(character) if use_xkb_actions else action_id
            records.append((target_action_id, sequence, normalized_when_line(match)))
    return records


def selected_additions(
    base: str,
    generated: str,
    limit: int,
    *,
    skip_colliding_roots: bool,
    use_xkb_actions: bool,
    max_utf16_units: int,
) -> dict[str, list[str]]:
    blocked_roots = blocked_root_states(base, generated) if skip_colliding_roots else set()
    records = generated_output_records(
        generated,
        blocked_roots,
        use_xkb_actions=use_xkb_actions,
        max_utf16_units=max_utf16_units,
    )[:limit]
    allowed: set[str] = set()
    outputs: dict[str, list[str]] = {}

    for action_id, sequence, raw_line in records:
        for index in range(1, len(sequence)):
            allowed.add(prefix_state(sequence[:index]))
        outputs.setdefault(action_id, []).append(raw_line)

    additions: dict[str, list[str]] = {}
    for action_id, body in ACTION_BLOCK_RE.findall(generated):
        character = action_character(action_id, body)
        target_action_id = xkb_action_id(character) if use_xkb_actions and character is not None else action_id
        for match in WHEN_RE.finditer(body):
            parsed = attrs(match.group(1))
            state = parsed.get("state")
            next_state = parsed.get("next")
            if state == "compose" and next_state in blocked_roots:
                continue
            if state == "compose" and next_state in allowed:
                additions.setdefault(target_action_id, []).append(normalized_when_line(match))
            elif state in allowed and next_state in allowed:
                additions.setdefault(target_action_id, []).append(normalized_when_line(match))

    for action_id, lines in outputs.items():
        additions.setdefault(action_id, []).extend(lines)
    return additions


def remove_compose_branches(body: str) -> str:
    kept_lines: list[str] = []
    for line in body.splitlines():
        when_match = WHEN_RE.search(line)
        if when_match is None:
            kept_lines.append(line)
            continue
        if attrs(when_match.group(1)).get("state") != "compose":
            kept_lines.append(line)
    return "\n".join(kept_lines)


def inject_additions(
    layout: str,
    additions: dict[str, list[str]],
    *,
    replace_compose_roots: bool,
) -> str:
    existing = {action_id for action_id, _ in ACTION_BLOCK_RE.findall(layout)}
    missing = sorted(set(additions) - existing)
    if missing:
        raise ValueError(f"missing action ids: {', '.join(missing[:20])}")

    def replace(match: re.Match[str]) -> str:
        action_id = match.group(1)
        lines = additions.get(action_id)
        if not lines:
            return match.group(0)
        body = remove_compose_branches(match.group(2)) if replace_compose_roots else match.group(2)
        return f'\n\t<action id="{action_id}">{body}\n' + "\n".join(lines) + "\n\t</action>"

    return ACTION_BLOCK_RE.sub(replace, layout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--working", required=True, type=Path)
    parser.add_argument("--generated", required=True, type=Path)
    parser.add_argument("--limit", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--xkb-only", action="store_true")
    parser.add_argument("--strict-xkb-actions", action="store_true")
    parser.add_argument("--keep-inert-old-states", action="store_true")
    parser.add_argument("--replace-compose-roots", action="store_true")
    parser.add_argument("--max-utf16-units", type=int, default=1)
    args = parser.parse_args()

    base = build_promotion_only(args.working.read_text(encoding="utf-8"))
    if args.xkb_only and args.strict_xkb_actions:
        base = build_xkb_only_base(base)
    elif args.xkb_only and args.keep_inert_old_states:
        base = build_xkb_semantics_compat_base(base)
    elif args.xkb_only:
        base = build_xkb_semantics_base(base)
    additions = selected_additions(
        base,
        args.generated.read_text(encoding="utf-8"),
        args.limit,
        skip_colliding_roots=not args.xkb_only and not args.replace_compose_roots,
        use_xkb_actions=args.xkb_only and args.strict_xkb_actions,
        max_utf16_units=args.max_utf16_units,
    )
    result = inject_additions(base, additions, replace_compose_roots=args.replace_compose_roots)
    args.output.write_text(result, encoding="utf-8")

    print(f"wrote {args.output}")
    print(f"actions with additions: {len(additions)}")
    print(f"when lines added: {sum(len(lines) for lines in additions.values())}")


if __name__ == "__main__":
    main()
