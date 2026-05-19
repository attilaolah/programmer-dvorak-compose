# macOS keylayout debugging

## Known baseline

The vendored `resources/programmer_dvorak_compose.keylayout` loads in macOS
Settings and works after installation.

Observed size/profile:

- 66 KB
- `maxout="1"`
- 64 actions
- 21 unique states
- 20 terminators

## Failing generated layout

The generated full-XKB layout does not appear as an available input source in
macOS Settings.

Observed size/profile:

- 192 KB
- `maxout="2"`
- 138 actions
- 1459 unique states
- 1210 terminators
- 26 multi-UTF-16-unit outputs
- 10 non-BMP outputs

The largest structural change is not bundle metadata. The generator promotes
many direct printable key outputs into actions so that those keys can also
participate in compose transitions. The generated layout has 474 key action
references, compared with 179 in the working layout.

## Experiment 1: promotion-only

Result: loads and works.

This test started from the working layout, kept the original compose actions
and terminators, and only promoted single printable `<key output="..."/>`
entries into simple pass-through `xkb_....` actions:

```xml
<action id="xkb_....">
  <when state="none" output="..." />
</action>
```

Observed profile:

- 89 `xkb_` pass-through actions
- 295 `xkb_` key references
- original compose state graph preserved
- original terminators preserved

Conclusion: macOS accepts the extra promoted key actions and key references.
The failure is more likely caused by the generated compose state graph, its
size, a specific generated output, or a specific generated transition.

## Experiment 2: one generated XKB output

Result: loads and works.

This test started from the promotion-only layout and added exactly two
generated `<when>` rules:

```xml
<when state="compose" next="xkb_s_0021" />
<when state="xkb_s_0021" output="Ạ" />
```

Verified sequence:

```text
Compose + ! + Shift-A -> Ạ
```

Conclusion: macOS accepts at least one generated XKB state and can use it at
runtime. The failure is not caused by the mere presence of an `xkb_s_....`
state name.

## Experiment 3: two generated XKB outputs

Result: crashes or otherwise prevents switching to the layout.

This test added four generated `<when>` rules:

```xml
<when state="compose" next="xkb_s_0021" />
<when state="xkb_s_0021" output="Ạ" />
<when state="compose" next="xkb_s_0022" />
<when state="xkb_s_0022" output="Ä" />
```

The likely cause is not the second generated state by itself. The generated
`xkb_s_0022` root transition was added to the existing `quote` action, which
already had an old compose transition:

```xml
<when state="compose" next="diaeresis" />
<when state="compose" next="xkb_s_0022" />
```

That creates two `<when state="compose" ... />` branches in one action. macOS
appears to reject or crash on this shape. The debug builder now skips generated
root compose states when the original action already owns `state="compose"`.

## Experiment 4: 50 generated XKB outputs

Result: does not load.

This test added 50 generated output transitions plus the intermediate state
transitions needed to reach them:

- 91 generated `<when>` rules
- 41 generated `xkb_` states
- 28 actions with generated additions

Conclusion: the failure appears somewhere between the one-output test and this
50-output subset, or from the shape of a rule included in the first 50 outputs.

## XKB-only direction

The old Programmer Dvorak compose/dead-key graph is not required for the target
layout. Keeping it while adding XKB roots caused root collisions such as
`quote` having both:

```xml
<when state="compose" next="diaeresis" />
<when state="compose" next="xkb_s_0022" />
```

The debug builder supports `--xkb-only`, which:

- keeps normal `state="none" output="..."` behavior
- keeps the compose key entry point
- removes original non-`none` compose/dead-key branches
- replaces original terminators with only the bare compose cancel terminator
- adds the selected generated XKB subset

This is the preferred direction: let XKB own compose semantics instead of
trying to merge two compose graphs.

### XKB-only two-output crash

Result: crashed Finder while activating the input source.

The relevant crash report was:

```text
~/Library/Logs/DiagnosticReports/Finder-2026-05-19-122427.ips
```

The faulting stack was in HIToolbox input-source activation:

```text
CFStringCompare
_TSMSetInputSourceSelected
MyActivateTSMDocument
-[NSTextInputContext activate]
```

The unified logs did not include a useful keylayout parser error. They only
showed the layout file being opened by `imklaunchagent`, followed later by
`TextInputMenuAgent` reporting `unknown input source id:<private>`.

The installed XKB-only file had six empty actions that were still referenced by
keys:

```text
acute
breve
circum
diaeresis
grave
nasal
```

Hypothesis: HIToolbox does not tolerate key actions with no `<when>` entries.
XKB-only generation must not leave referenced original dead-key actions empty.
It should either replace those key references with generated/pass-through
actions or give those actions valid `state="none" output="..."` behavior.

### Strict XKB-only action model

The next XKB-only variant rewrites all key references to old printable actions
to `xkb_....` actions, then removes the old printable/dead-key actions.

For old dead-key actions whose default character was expressed as
`state="none" next="..."`, the debug builder derives the default output from
the original terminator table. For example:

```xml
<when state="none" next="acute" />
...
<when state="acute" output="´" />
```

becomes a key reference to:

```xml
<action id="xkb_00b4">
  <when state="none" output="´" />
</action>
```

The strict XKB-only two-output test has:

- no old non-`xkb_` action IDs except `compose`
- no key references to missing actions
- no empty action blocks
- no old non-XKB states

Result: loads, but the test compose sequences do not produce output. The
state-specific output rules were on synthetic actions such as `xkb_0041`.
Hypothesis: HIToolbox accepts these synthetic actions for pass-through and
root transitions, but not as reliable targets for state-specific output.

### XKB semantics with compatibility action IDs

The next variant keeps old action IDs only as pass-through compatibility
wrappers, while removing old compose semantics:

- old `state="none" output="..."` behavior is preserved
- old `state="none" next="..."` dead-key behavior is converted to direct
  `state="none" output="..."` using the original terminator output
- all non-`none` old compose/dead-key branches are removed
- generated XKB compose rules are attached to the old action IDs

This still has XKB-only compose semantics, but avoids using synthetic `xkb_....`
actions as the final state-specific output targets.

Result: loads, but pressing the compose key did not appear to enter compose
state; sequences printed literally. The root and final transition blocks for
`Compose + ! + Shift-A` matched the earlier working test, so the likely
difference is that too much old action/state shape was removed.

### XKB semantics with inert old states

The next variant removes old compose entry points but keeps old state-specific
output branches as inert compatibility data:

- `state="compose"` branches from the original layout are removed
- original `state="none" next="..."` dead-key entries are converted to direct
  `state="none" output="..."` entries
- original state-specific output branches such as `state="acute"` are kept,
  but should be unreachable because the entry points are gone
- generated XKB `state="compose"` roots are added

This preserves more of the action shape from the known-working layout while
still preventing old compose sequences from being entered.

Result: loads, but compose state still did not appear to activate. Removing
most original `state="compose"` branches seems to make HIToolbox stop honoring
the compose state, even though the `compose` action itself remains present.

### Replace old roots instead of removing the graph

The next variant returns to the known-working shape and keeps the original
compose graph as compatibility scaffolding. For XKB roots that collide with an
old root, the old `state="compose"` branch in that action is replaced instead
of duplicated.

For example, `quote` becomes:

```xml
<action id="quote">
  <when state="none" output="&quot;" />
  <when state="less" output="“" />
  <when state="greater" output="”" />
  <when state="compose" next="xkb_s_0022" />
</action>
```

This should avoid both failure modes seen so far:

- duplicate `state="compose"` branches in one action
- loss of compose behavior after stripping most old compose branches

Result: works.

Verified outputs:

```text
Compose + ! + Shift-A -> Ạ
Compose + " + Shift-A -> Ä
Compose + ' + Shift-A -> Á
Compose + ' + ^ + Shift-A -> Ấ
Compose + < + " -> “
Compose + > + " -> ”
```

This is the current winning approach. It keeps the original compose graph as
HIToolbox compatibility scaffolding, but replaces colliding root branches with
generated XKB roots instead of appending duplicates.

### Numeric output escaping

The generated debug variants initially used named XML entities such as
`&amp;` in synthetic pass-through actions. Normal `&` output then failed in the
installed layout even though the action existed:

```xml
<action id="xkb_0026">
  <when state="none" output="&amp;" />
</action>
```

The working layout historically uses numeric escapes for these characters, so
the debug builder now emits numeric escapes instead:

```xml
<action id="xkb_0026">
  <when state="none" output="&#x26;" />
</action>
```

Use numeric escapes for XML-sensitive output characters in generated keylayout
files.

### Working checkpoint: limit 4

Status: working.

Installed profile:

- root-replacement approach
- first 4 generated XKB output records
- numeric output escaping
- 8 generated `<when>` rules
- no duplicate action IDs
- no missing key action references
- no empty action blocks

Verified:

```text
&                         -> &
Compose + ! + Shift-A     -> Ạ
Compose + " + Shift-A     -> Ä
Compose + ' + Shift-A     -> Á
Compose + ' + ^ + Shift-A -> Ấ
```

This is the baseline to revert to if later batches crash Finder or make the
layout unavailable.

### Batch import status

Using the root-replacement approach with numeric escaping:

- limit 4: working checkpoint
- limit 8: no Finder/input-source crash on quick switch test
- limit 16: no Finder/input-source crash on quick switch test
- limit 32: no Finder/input-source crash on quick switch test
- limit 64: no Finder/input-source crash on quick switch test
- limit 128: no Finder/input-source crash on quick switch test
- limit 256: no Finder/input-source crash on quick switch test
- limit 512: no Finder/input-source crash on quick switch test
- limit 1024: no Finder/input-source crash on quick switch test
- limit 2048: no Finder/input-source crash on quick switch test
- limit 4096 with `--max-utf16-units 1`: identical to limit 2048; the
  single-UTF-16-unit generated output set is exhausted

The next axis is output width. Raising the builder to `--max-utf16-units 2`
adds 13 generated output records beyond the single-unit set. In the current
generated file these include 8 multi-codepoint outputs and 5 non-BMP
characters.

- limit 4096 with `--max-utf16-units 2`: no Finder/input-source crash on quick
  switch test

Inventory after the two-unit build:

- 1209 generated terminal compose output records parsed
- 1209 unique generated terminal sequences
- UTF-16 output width distribution: 1196 one-unit outputs, 13 two-unit outputs
- no generated output `<when>` rules skipped by the debug converter

Representative two-unit sequences:

```text
Compose + p + o + o       -> 💩
Compose + \ + o + /       -> 🙌
Compose + L + L + A + P   -> 🖖
Compose + ( + ) + )       -> 🄯
Compose + F + U           -> 🖕
```

Conclusion: for the current generated keylayout data, the
root-replacement variant with numeric escaping and two-UTF-16-unit outputs
imports every generated terminal sequence that the debug converter can see,
without triggering the input-source crash in quick switch tests.

## Bisection method used

Build variants from the working layout, not by deleting arbitrary lines from
the generated layout:

1. Start with the promotion-only layout.
2. Add a closed subset of generated `xkb_` compose sequences.
3. Keep only transitions whose source and destination states are in that
   subset.
4. Keep only terminators for selected terminal `xkb_` states.
5. Grow the selected sequence count until macOS rejects the layout.
6. If the failure appears early, bisect by generated sequence index or by
   output category: non-BMP outputs, multi-codepoint outputs, long sequences,
   and high-fanout prefixes.
