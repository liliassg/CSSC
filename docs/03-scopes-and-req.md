# 03 — Scopes & `#req`

CSSC scoping is **not** C scoping. The single rule that surprises people:

> Some blocks are **isolation barriers** — code inside them cannot see outer
> names at all, and must import what it needs with `#req`. Other blocks are
> **transparent** — they see the enclosing scope directly.

Getting this wrong produces the classic "why is my variable `0x0` inside this
block?" bug. This chapter is the definitive list.

---

## 1. The scope model

- **The top level is one flat scope.** All top-level `#stack`/`#heap`/`#auto`
  declarations and all top-level `#define` functions live together in it.
- **Barriers install a fresh frame** on entry and restore the previous one on
  exit. Names declared inside a barrier do not leak out; names outside a barrier
  are not visible in (except via the resolution rules in §3).
- **Non-barriers do not install a frame** — they read and write the enclosing
  scope directly.

---

## 2. Isolation barriers vs non-barriers

| Construct | Barrier? | Sees enclosing scope? | Inner **names** gone after `}`? |
|---|---|---|---|
| `#define(f) { … }` body | **Barrier** | No — import via `#req` | Yes |
| `#cdefine(f, …) { … }` body | **Barrier** | No — import via `#req` | Yes |
| bare `{ … }` block | **Barrier** | No — import via `#req` | Yes |
| object body | **Barrier** | No (has own members) | Yes (members live until `#free`) |
| label body | **Barrier** | Object members via implicit `this`; else `#req` | Yes |
| sector body | **Barrier** | No (has own members + `<deps>`) | Members live until `#free` |
| `if` / `else` block | Not a barrier | **Yes** | its own locals released at `}` |
| `for ( … ) { … }` | Not a barrier | **Yes** | loop var + locals released at `}` |
| `while ( … ) { … }` | Not a barrier | **Yes** | its locals released at `}` |
| `select ( … ) ?n { … }` | Not a barrier | **Yes** | `?n` cursor released at `}` |

Mnemonic: **`#define`, `{}`, object, label, sector = walls. `if`, `for`, `while`,
`select`, `else` = windows.**

> **Names vs buffers.** This table is about **name visibility** — whether an
> identifier is reachable. It is *not* the same as when the underlying memory is
> freed. In R2 only the bare `{}` block auto-discards the `#heap` it created at
> `}`; a `#define` body restores its names but leaves `#stack`/`#auto` buffers
> for you to `#delete` (and `#heap` until program end). See
> [02-memory-and-ownership §3](02-memory-and-ownership.md).

```cssc
#stack[int, 32] x = 50;

if (x < 100) {
    cssc::outln(x);      // -> 50   (if is a window: sees outer x)
}

{
    cssc::outln(x);      // -> 0x0  (bare {} is a wall: x is invisible here)
}

{
    #req[x] xr;          // import x across the wall (live ref by default)
    cssc::outln(xr);     // -> 50
}
```

> **Common mistake.** Treating a bare `{ … }` like a C block. In C it sees the
> enclosing scope; in CSSC it is a wall. Use `#req` to bring names in.

---

## 3. Name resolution inside a barrier

Inside a barrier body, an **unqualified** identifier resolves in this order:

1. **barrier-local** declarations (this frame),
2. **`#req` imports** declared in this body,
3. **parameters** (`#scanp`, label params) and **`<deps>`** injected into a
   sector/object,
4. **`cssc::` built-ins**,
5. the barrier's **own members** (sector/object members, via `->` or implicit).

A bare, unqualified name that matches none of these does **not** fall back to the
global scope. In a sector function, an unknown bare name resolves to `0x0` (null)
— there is no accidental global read/write.

> **Impl-canonical note.** There is deliberately **no** implicit outer-scope
> fallback across a barrier. This is a feature: it prevents a function from
> silently reading or clobbering an unrelated top-level slot. If you need an outer
> name, import it with `#req` (or, for sectors/objects, inject it via `<deps>`).

---

## 4. `#req` — import across a barrier

`#req` is the only way to pull an outer name into a `#define`/`{}` body. It comes
in two forms:

| Form | Meaning |
|---|---|
| `#req[X] Y;` | **Live reference (default).** `Y` reads *and writes through* to `X`. `Y += 1` really increments `X`. |
| `#req[X] &Y;` | **Snapshot (deep copy).** `Y` is an independent frozen copy of `X` at import time. Writes to `Y` do **not** touch `X`. For scalars this is indistinguishable from a ref; for `string`/`vector`/`map`/`bind`/objects/sectors it is a recursive deep copy. |
| `#req[X] *Y;` | **Deprecated** legacy spelling of the live-ref form. Identical semantics to `#req[X] Y;`. New code omits the `*`. |

```cssc
#stack[int, 32] hits = 0;

#define(beat) {
    #req[hits] h;      // live ref -> mutating h mutates hits
    h += 1;
}

beat();
cssc::outln(hits);     // -> 1   (write went through the ref)
```

Snapshot form:

```cssc
#stack[int, 32] cfg = 10;

#define(readonly) {
    #req[cfg] &c;      // snapshot: c is a private copy
    c = 999;           // does NOT touch cfg
}

readonly();
cssc::outln(cfg);      // -> 10
```

> **Impl-canonical note.** `#req` is **ref-by-default**. This matches the
> argument-passing default (`f(x)` is ref) — see
> [04-callables](04-callables.md). The write-back is real: `#delete[Y]` inside the
> body invalidates the outer `X` too (cross-frame delete, one level — see
> [02-memory-and-ownership §5.1](02-memory-and-ownership.md)).

> **Migration note.** Pre-v6, `#req[X] Y;` meant *snapshot* and `#req[X] *Y;`
> meant *ref*. That is flipped now: bare `Y` is the ref, `&Y` is the snapshot,
> and `*Y` is a deprecated alias of the ref. If you are porting old code that
> relied on `#req[X] Y;` being a copy, change it to `#req[X] &Y;`.

---

## 5. Importing other functions with `#req`

Top-level `#define` functions are just variables in the flat top scope, so they
are imported the same way. After importing, call through the alias.

```cssc
#stack[int, 32] helper;
#define(helper) { return 7; }

#stack[int, 32] caller;
#define(caller) {
    #req[helper] h;          // import the function
    #stack[int, 32] r = h(); // call it -> 7
    return r;
}
```

---

## 6. `#DEFINE` (uppercase) — a compiler/transpiler construct

`#DEFINE` (uppercase) is **not** `#define` (lowercase). Lowercase `#define`
declares a callable (see [04-callables](04-callables.md)). Uppercase `#DEFINE` is
a **compiler/transpiler directive** with three uses:

```cssc
#DEFINE __main__ '__main__';   // entry-point opt-in
#DEFINE somename;              // foreign-namespace passthrough
#DEFINE MAX <expr>;           // compile-time constant (native/transpiler path)
```

> **Impl-canonical note.** In the R2 interpreter, `#DEFINE` is a **runtime
> no-op** — it does not create a substituted constant you can read at run time.
> Its "compile-time constant" meaning applies to the native/transpiler path, not
> `cssc run`. Do not rely on `#DEFINE NAME value;` expanding inside interpreted
> code; use a real `#stack`/`#heap` slot for a runtime value.

Case matters: `#DEFINE` = compiler construct, `#define` = function. See
[08-directives](08-directives.md) for both, and for `#redefine` (function body
mutation, interpreter-only).

---

## Common mistakes / impl-canonical notes

- **Bare `{}` is a wall, not a window.** Inner code cannot see outer names —
  import with `#req`.
- **`if`/`for`/`while`/`select` ARE windows.** They see the enclosing scope; you
  do **not** need `#req` inside them.
- **No global fallback across a barrier.** An unknown bare name in a sector
  function is `0x0`, not the top-level variable of the same name.
- **`#req` default is a live ref, not a copy.** Use `&` for a snapshot. This is
  the reverse of pre-v6 semantics.
- **`#DEFINE` ≠ `#define`.** Uppercase = constant, lowercase = function.

## See also

- [02-memory-and-ownership](02-memory-and-ownership.md) — aliasing, delete cascade, barrier discard of heap.
- [04-callables](04-callables.md) — `#define`, parameters, call-site ref/copy.
- [06-sectors](06-sectors.md) — sector bodies as barriers, `<deps>` injection.
- [05-objects](05-objects.md) — object/label bodies as barriers.
