# 01 — Types & Values

CSSC is strictly typed at declaration, RAW at runtime, and deterministic about
sizes. This chapter is the authority on what the primitive types are, how big they
are, what `null` means, and how the container types behave.

---

## 1. Primitive types

| Type | Runtime representation | Size |
|---|---|---|
| `int` | Python-style big integer | **Arbitrary precision** (encoded as minimal signed little-endian bytes) |
| `float` | IEEE-754 double | **Always 64-bit** (8 bytes) — never 32-bit |
| `string` | UTF-8 text | Variable (byte length of the UTF-8 encoding) |
| `bool` | single byte | **1 byte** (`sizes` still recommends 8 bits) |
| `auto` / `var` / `void` | untyped | whatever the initializer produced; default `null` |

```cssc
#stack[int, 32]   n = 42;       // also 0xFF, 0b1010
#stack[float, 64] f = 3.14;     // must be >= 64 bits (see §2)
#stack[string, 128] s = "hi";   // "double" or 'single' quotes
#stack[bool, 8]   b = true;     // true / false
```

---

## 2. `float` has a hard 64-bit floor — by rejection, not promotion

A `float` always encodes to 8 bytes. `#stack[float, N]` with `N < 64` does **not**
get silently rounded up to 64 — it is **rejected** at declaration with an
overflow error (`value exceeds bit limit`), even for the default `0.0`.

```cssc
#stack[float, 64] ok = 3.14;    // fine (minimum spec)
#stack[float, 32] bad = 1.0;    // ERROR: 64 > 32 bits
```

This deliberately prevents a silent float32/float64 mismatch. The minimum valid
float declaration is `#stack[float, 64]`.

> **Watch out with `sizes`.** `sizes::small_float` is `32` (see §6). Using it for a
> `float` slot (`#stack[float, sizes::small_float]`) triggers the floor rejection.
> Use `sizes::normal_float` (64) or larger for floats.

---

## 3. `char`, `byte`, `i32`, `i64`, `f32`, `f64`, `double` are NOT first-class

Only `int`, `float`, `string`, `bool`, the containers, and `auto`/`var`/`void`
are real types. Any other type name — including `char`, `byte`, `i32`, `i64`,
`f32`, `f64`, `double` — is **not normalized to a real type**. It degrades to an
untyped/`auto` passthrough:

- no coercion (the value keeps whatever type its initializer produced),
- no default value (defaults to `null`),
- no strict type-checking (anything is accepted).

```cssc
#stack[i32, 32] x = 5;   // 'i32' is NOT int; x is an untyped passthrough of 5
#stack[char, 8] c = "A"; // 'char' is NOT a distinct type; c is just the string "A"
```

> **Common mistake.** Reaching for `i32`/`u8`/`char` expecting C semantics. They
> are accepted syntactically but give you an untyped slot, not a sized integer or
> a character type. Use `int`, and control width with the `bits` capacity.

---

## 4. `null` vs `0x0`

Both are the **same null sentinel**.

- `null` (and its alias `none`) evaluate to the null value.
- `0x0` is the integer `0`, and CSSC treats `null == 0` and `null == 0x0` as
  **true** for `==`/`!=`.
- A deleted/dangling slot reads back as `0x0`.

```cssc
if (maybe == 0x0) { /* maybe is null / unbound / zero */ }
if (maybe == null) { /* identical test */ }
```

So `0x0` is the idiomatic "is it there?" guard (also used with `#adress` — see
[02-memory-and-ownership §9](02-memory-and-ownership.md)).

---

## 5. Literals

| Kind | Forms |
|---|---|
| int | `42`, `0xFF`, `0b1010` |
| float | `3.14`, `2.0` |
| string | `"hello"`, `'world'` |
| bool | `true`, `false` |
| null | `null`, `none`, `0x0` |
| array | `{1, 2, 3}` **or** `[1, 2, 3]` (see §7) |
| map | `{}`, `{key: value}`, `{key = value}` |
| bind | `{a, b; c, d}` (has a `;`) |

---

## 6. Capacities and the `sizes` module

The `bits` argument to `#stack`/`#heap` is a **capacity in bits**. Defaults when
omitted:

| Region | Default |
|---|---|
| `#stack[type]` | **256 bits** |
| `#heap[type]` | **1024 bits** |
| `#auto[type]` | **min 32 bytes** (256 bits), grows on demand |

For **containers** (`array`/`vector`/`map`/`bind`), the second argument is an
**element capacity**, not a scalar bit-limit.

The `sizes` module gives readable, recommended bit counts. `#include("sizes")
sz;`, then use `sz::name` anywhere a size is expected:

```cssc
#include("sizes") sz;
#stack[string, sz::normal_string] name = "Ada";   // 256 bits
#stack[int, sz::large_int] big = 0;                // 64 bits
```

Full constant table (bits):

| group | `small_` | `normal_` | `large_` |
|---|---|---|---|
| `int` | 16 | 32 | 64 |
| `float` | 32 | 64 | 128 |
| `string` | 128 | 256 | 1024 |
| `bool` | 8 | 8 | 8 |
| `array` / `vector` / `list` | 256 | 1024 | 4096 |
| `map` / `dict` | 512 | 2048 | 8192 |
| `auto` / `var` | 64 | 256 | 1024 |

(e.g. `sz::normal_string` = 256, `sz::large_map` = 8192.)

---

## 7. Containers — array, vector/list, map, bind

CSSC has four container shapes. The literal you write and the **runtime type** you
get are not always the class you'd guess:

| You write | Parses as | Runtime type in R2 |
|---|---|---|
| `{1, 2, 3}` (no `;`, no `:`/`=`) | array literal | **native list** |
| `[1, 2, 3]` | array literal | **native list** |
| `{k: v}` or `{k = v}` or `{}` | map literal | **native dict** |
| `{a, b; c, d}` (has a `;`) | bind literal | **`CsscBind`** |

> **Impl-canonical note.** `{…}` and `[…]` **both** produce a plain list at
> runtime — the brace vs bracket choice does not change the literal's type. The
> dedicated `CsscArray` / `CsscVector` / `CsscMap` classes (with their richer
> method sets) appear only when a value is assigned into a **typed** slot
> (`array<T>` / `vector<T>` / `map<K,V>`), passed through coercion, or built by
> the `#array`/`#vector`/`#map` directives. Legacy docs implying `{…}` is always a
> `CsscArray` and `[…]` always a `CsscVector` are imprecise: the *slot type*
> decides, not the bracket.

Method availability follows from that:

- **`array<T>`** (native list / `CsscArray`): `push_back`, `pop_back`,
  `push_front`, `pop_front`, `size`, `length`, `at`, `get`, `set`, `contains`,
  `indexOf`, `insert`, `erase`, `slice`, `join`, `sort`, `reverse`, `unique`,
  `first`, `last`, `front`, `back`, `clear`, `resize`, `capacity`, … (typed
  `CsscArray` adds `map`/`filter`/`reduce`/`sum_val`/`sortBy`/… ).
- **`vector<T>` = `list`** (`CsscVector`): the full STL-ish surface —
  `push_back`/`pop_back`/`front`/`back`/`at`/`insert_at`/`erase`/`resize`/
  `reserve`/`capacity`/`map`/`filter`/`reduce`/`slice`/`sort_inplace`/… .
- **`map<K,V>`** (native dict / `CsscMap`): `get`, `set`, `has`, `contains`,
  `keys`, `values`, `items`, `remove`, `size`, `length`, `clear`, `merge`,
  `update`, `at`, … (typed `CsscMap` adds `emplace`/`get_or_default`/
  `lower_bound`/… ).

Assignment aliasing for containers (they alias, scalars value-copy) is in
[02-memory-and-ownership §8](02-memory-and-ownership.md).

---

## 8. `bind` — the structured key/cell type

A `bind` stores a flat cell list plus a `pair_width` that says how many cells make
one "pair" (row). This enables both flat `b[i]` and 2-D `b[r][c]` access over the
same data.

- **Structured literal** `{a, b; c, d}` -> `pair_width = cells in the first pair`.
  `{a, b; c, d}` -> `pair_width = 2`; `{a, b, c; d, e, f}` -> `pair_width = 3`.
  All pairs must have the same cell count.
- **Flat `{a, b, c}` is an *array* literal, not a bind** — it becomes a `bind`
  only when assigned/coerced into a `bind` slot, and that coercion pairs adjacent
  cells -> **`pair_width = 2`** (a trailing unpaired cell becomes `(cell, null)`).
- `pair_width = 0` happens only for an empty/default bind.

> **Impl-canonical note.** A "flat bind" ends up with **`pair_width = 2`**, not
> `0`, in R2. Older tables claiming a flat literal yields `pair_width 0` are
> wrong: a flat `{a,b,c}` is an array until coerced, and coercion pairs it at
> width 2.

Access and size:

- `b[i]` — flat access to the i-th cell.
- `b[r][c]` — structured access, equal to `b[r * pair_width + c]`.
- `b.size()` / `b.length()` — number of **pairs** (entries), not cells.
- `b.addmap(m)` — append a map/pair/list's entries as pairs. Other list methods
  (`push_back`, `pop_back`, `at`, …) work because `bind` is a list subclass.

```cssc
#heap[bind, 328] frame = {yPos, text; durationMs, 0x0};  // pair_width = 2
cssc::outln(frame[0]);       // yPos        (flat cell 0)
cssc::outln(frame[2]);       // durationMs  (flat cell 2)
cssc::outln(frame[1][0]);    // durationMs  (row 1, col 0)
cssc::outln(frame.size());   // 2           (pairs, not cells)
```

---

## 9. Strings

`string` is UTF-8 and has a large method surface:

`length`, `size`, `upper`, `lower`, `trim`, `split(sep=' ')`, `replace(old,new)`,
`contains`, `startsWith`/`starts_with`, `endsWith`/`ends_with`,
`indexOf`/`index_of`/`index`, `charAt`, `substr(start, len=-1)`,
`substring(start, end=-1)`, `reverse`, `repeat`, `padStart(n, ch)`,
`padEnd(n, ch)`, `isEmpty`, `isDigit`, `isAlpha`, `toInt`, `toFloat`, `front`,
`back`, `data`, `capacity`, `exists`.

Indexing and mutation:

```cssc
#stack[string, 128] s = "Hello";
cssc::outln(s[1]);        // -> "e"   (a 1-character STRING, not a code point)
s[0] = "h";               // in-place single-char mutation -> "hello"
cssc::outln(s.length());  // -> 5
```

- `s[i]` returns a **1-character string** (out-of-range yields `""`).
- `s[i] = "x"` rebuilds the string (strings are immutable underneath); writing
  past the end zero-pads with `\x00`. The target must be a named variable.
- `indexOf`/`index_of` return `-1` when not found; `toInt`/`toFloat` return
  `0`/`0.0` on non-numeric input.

---

## Common mistakes / impl-canonical notes

- **`float` under 64 bits is an error, not a rounding.** Minimum is
  `#stack[float, 64]`. `sizes::small_float` (32) will be rejected for a float.
- **`i32`/`char`/`byte`/`double` are not real types** — they silently become
  untyped slots. Use `int`/`float` with a `bits` capacity.
- **`0x0` == `null` == `0`.** All three compare equal; `0x0` is the standard
  null/unbound guard.
- **`{…}` and `[…]` are both lists at runtime.** The typed slot, not the bracket,
  decides whether you get a `CsscArray`/`CsscVector`.
- **A flat bind is `pair_width 2`, not 0**, and a flat `{a,b,c}` is an array until
  coerced into a bind slot.
- **`s[i]` is a 1-char string**, not an integer character code.

## See also

- [02-memory-and-ownership](02-memory-and-ownership.md) — capacities, container aliasing, `null`/`0x0` guard.
- [08-directives](08-directives.md) — `#string`/`#int`/`#array`/`#vector`/`#map` typed-declaration directives.
- [07-modules](07-modules.md) — `#include("sizes")` and other modules.
