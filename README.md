# CSSC

**Control Specified Source Compiling** — a small, hardware-near language where you
decide when a variable exists, how wide it is, how long it lives, and when it's
checked. Nothing is hidden from you, and nothing is done behind your back.

This is the authoritative language reference: the exact rules, minimal examples
that were actually run, and an explicit log of every place the older prose
disagreed with the implementation. It documents what CSSC *does*, not what it was
supposed to do — and where those two differ, both are written down.

---

## Where to start

- **New here?** Read 01 → 02 → 03 in order. Chapter 02 (memory) is the one that
  decides whether your programs work; everything else is comfort.
- **Debugging something that "should" work?** Go straight to
  [Rules people get wrong](#the-rules-people-get-wrong).
- **Wondering why a doc you read elsewhere lied to you?** See the
  [conflict log](#doc--impl-conflict-log).

| # | File | What's in it |
|---|---|---|
| 00 | **README** (this file) | Index, vision, toolchain, precedence rule, conflict log. |
| 01 | [01-types-and-values.md](01-types-and-values.md) | Primitive types & sizes, `null`/`0x0`, literals, the `sizes` module, containers (array/vector/map/bind). |
| 02 | [02-memory-and-ownership.md](02-memory-and-ownership.md) | **Highest stakes.** `#stack`/`#heap`/`#auto`, exact free timing, `#delete`/`#delmember`/`#free`, the delete cascade, aliasing. |
| 03 | [03-scopes-and-req.md](03-scopes-and-req.md) | Isolation barriers vs transparent blocks, name resolution, `#req` (ref vs `&` snapshot), `#DEFINE`. |
| 04 | [04-callables.md](04-callables.md) | `#define`/`#cdefine`, parameters, call-site ref/copy, `mirror` vs `return`, the variable-is-function duality. |
| 05 | [05-objects.md](05-objects.md) | `object` structure, `->` members, `.` labels, overloading, constructor params, `secure !` (inert in R2). |
| 06 | [06-sectors.md](06-sectors.md) | `sector` namespaces, `::` public/private enforcement, isolation, dependency injection, deferred init. |
| 07 | [07-modules.md](07-modules.md) | `#include`/`#load`/`#depend`/`#unload`, the `::` dispatch asymmetry, module search dirs. |
| 08 | [08-directives.md](08-directives.md) | Full `#…` directive table, grouped, with module gates and backend notes. |
| 09 | [09-control-flow.md](09-control-flow.md) | `if`/`for`/`while`, `select` + `jump` cursor iteration, `break`/`continue`. |
| 10 | [10-access-operators.md](10-access-operators.md) | The definitive `::` vs `->` vs `.` rules — the #1 source of mistakes. |

New topics get their own numbered file and a row in this table. The reference
grows modularly; nothing gets bolted onto an existing chapter because it was
"kind of related".

---

## What CSSC is for

- **Performance you can point at.** Speed is a benchmarked feature, not an
  assumption. Hot paths go native and the compiler is aggressive about
  dead-code elimination.
- **Everything RAW.** No garbage collector, no implicit bounds checks, no hidden
  copies, no automatic scope cleanup — the sole exception being `#heap` at
  program end. You allocate in bits and you free explicitly. On a
  microcontroller, you want to know where every bit went.
- **Tiny binaries.** Aggressive DCE plus a minimal runtime.
- **One source, many backends.** The same `.cssc` runs on the interpreter,
  compiles to native host code and to embedded targets (ESP32 / ESP8266 /
  Arduino / Raspberry Pi), and transpiles (e.g. to Luau).
- **Deterministic.** Sizes, layout, and evaluation order are predictable.
  Determinism is what buys efficiency *and* readability at the same time — you
  can reason about exactly what the machine will do, in your head, without
  running it.
- **Kernel-capable.** The RAW deterministic model is meant to reach all the way
  down to bare metal and ISR-level code (`#interrupt`, GPIO, and friends).

### The trade

The language does exactly what you wrote — including leaking the memory you
forgot to free, and including cascading a delete further than you expected. It
will not save you. The rules in these chapters are the contract that makes that
worth relying on: they're specific enough that "exactly what you wrote" is a
thing you can predict rather than discover.

---

## Toolchain

| Command | What it does |
|---|---|
| `cssc run <file>` | **Interpreter** (stage-0, pure Python). The behavioral oracle — R2 is what runs here. |
| `cssc build <file> [-o out]` | **Native compiler.** Host target needs LLVM ≥ 17. Embedded via `--esp32` / `--esp8266` / `--arduino` / `--raspberry`; `--gcc` is the legacy host path. |
| `cssc native --target host` | Native build (LLVM ≥ 17). |
| `cssc analyze <file> --raw`<br>`cssc lsp diagnostics <file>` | **Static analysis** (pure Python) — diagnostics and lints, e.g. `SELECT_WITHOUT_JUMP`, `TRANSIENT_LITERAL_IN_CALL_ARG`. |
| `cssc convert <file> --luau` | Transpile to another backend. |
| `cssc install …` / `cssc module install …` | Build and distribute `.obj` packages and installable modules. |

Three implementations have to agree on everything in these docs: the
**interpreter**, the **native compiler**, and the **LSP** analyzer. Where a
behavior exists on only one of them, the chapter says so out loud — see the
backend restrictions in the conflict log for the current list.

---

## The rules people get wrong

If you internalise nothing else, internalise these.

| Looks like | Actually does | Chapter |
|---|---|---|
| `b = a` | Scalars and strings are **value-copied**. Only containers alias. Live cross-slot links come from `#req` or argument passing — never from plain assignment. | [02 §8](02-memory-and-ownership.md) |
| `#delete[p]` on a reference | Cascades up the **whole** ref-link chain, not one level. (Ref-parameter *mutation* write-back is the single-level one — easy to swap in your head.) | [02 §5.1](02-memory-and-ownership.md) |
| `#heap` in a block | Frees at **program end**, not block exit. The one exception: a bare `{}` block discards the heap it created at its `}`. | [02 §3](02-memory-and-ownership.md) |
| An inner scope | `#define` / `{}` / object / label / sector are **barriers** — outer names are hidden, import them with `#req`. `if` / `for` / `while` / `select` / `else` are **windows** — they see the enclosing scope. | [03](03-scopes-and-req.md) |
| `f(x)` vs `f(&x)` | The **call site** decides: `f(x)` passes a reference, `f(&x)` passes a copy. A callee `&param` hint is ignored entirely. | [04 §7](04-callables.md) |
| `::` / `->` / `.` | Three different operators, not three spellings of one. `->` is **not** access-checked. | [10](10-access-operators.md) |
| `secure !`, object `private:` | **Inert in R2.** A "private" object label is still callable. Use a **sector** if you want privacy that's enforced. | [05 §7](05-objects.md) / [06](06-sectors.md) |
| `select` without `jump` | The cursor never advances. Backward is `!jump`; there is no `jump_back`. | [09 §5](09-control-flow.md) |
| `#stack[float, 32]` | Rejected. `float` is always 64-bit — sub-64-bit floats error out rather than getting promoted, even for `0.0`. | [01 §2](01-types-and-values.md) |
| `cssc::outln("hi")` | Legal, and the literal is **transient** — no owning slot, so it dies when the call returns. Copy it into an owning slot with `&` to keep it. | [02](02-memory-and-ownership.md) |

---

## Precedence: what counts as true

When sources disagree, this is the order:

1. **R2 behavior** (`cssc run`) — the oracle. If R2 does it, it's documented here
   as canonical, even when it contradicts the design intent.
2. **These chapters.**
3. **Older prose docs and the maintainer's fact sheet** — historical, superseded
   wherever the log below says so.

That order is a documentation rule, not an endorsement. Two entries below are
places where R2 and the intended design genuinely disagree; they're marked ⚠ and
are waiting on a decision, not on more writing.

**Terms:** *R2* is the current runtime revision — what `cssc run` executes.
*R1* is the previous revision, still present in the source as dead code; where
the log cites a line number in R1, that path no longer executes.

---

## Doc ↔ impl conflict log

Nineteen places where earlier docs disagreed with the implementation. Two of them
(#1, #2) contradict the maintainer's own fact sheet and need a call; the other
seventeen are simply corrected here.

### ⚠ Needs a decision

**1. The `#delete` cascade runs the opposite direction from the fact sheet.**
The fact sheet (and the task brief) say: `#delete` cascades exactly one caller
level, assignment write-back cascades all levels. R2 does the reverse.
`_delete_cross_frame` (line 17451) recurses the entire ref-link chain, capped at
16 levels — its own docstring documents the N-level `p→q→y` cascade — while
ref-parameter mutation write-back on return is single-level. The one-level delete
is dead R1 code (line 8710). Documented per R2 in
[02 §5.1](02-memory-and-ownership.md). **If one-level delete is the intended
design, R2 is what needs changing, not the docs.**

**2. Object access control is inert.** The enforcement code for `secure !` and
object `private:` exists, but it's gated on `_access_enabled`, which initialises
`False` and is never set `True` anywhere in the tree. So `secure !` does nothing
and a private object label is still callable — it does *not* return `0x0`. Legacy
docs showing `c.secret() -> 0x0` describe intent, not behavior. Documented in
[05 §7](05-objects.md); use sectors for real privacy.

### Corrected from the prose docs

**3. `b = a` aliasing.** Legacy §8.1/§8.4 claim plain assignment creates a live
reference even for `int`/`string`. It doesn't — scalars and strings are
value-copied, only containers alias. → [02 §8](02-memory-and-ownership.md)

**4. `->` is not access-checked.** A private sector member is hidden from a `::`
read but fully readable *and writable* through `->`. → [10](10-access-operators.md) / [06 §2](06-sectors.md)

**5. `Sector::member = v` persists.** `cssc-sectors.md` S12 calls it a silent
no-op; R2 writes it. (That doc is describing the native/transembly dead-write
model.) → [06 §2](06-sectors.md)

**6. Sector `<A: B>` is variable injection, not a typed constructor param.** For
sectors, `<outerVar: localName>` injects the outer variable under a local name.
Typed constructor params (`<int: width>`) are **object**-only. Legacy §6.3 and a
stale docstring both got this wrong. → [06 §4](06-sectors.md)

**7. `free {}` / `#free` are optional and unenforced.** Docs call them mandatory;
there is no leak check and no error if you skip them. Still best practice, and
`.obj` `#free` genuinely matters for compiled builds. → [06 §6](06-sectors.md)

**8. Builtin-module `#free` is a no-op.** Real module teardown is `#unload`
(paired with `#load`/`#depend`). Docs implying every `#include` needs a matching
`#free` are wrong. → [07 §6](07-modules.md)

**9. `alias::member` fails asymmetrically.** A missing **builtin-module method
call** is a hard error; a private or missing **sector** member is a silent
`null`. → [07 §3](07-modules.md) / [10](10-access-operators.md)

**10. `{…}` and `[…]` are both native lists at runtime.** The typed slot decides
whether you get a `CsscArray` or a `CsscVector` — the bracket you typed doesn't.
→ [01 §7](01-types-and-values.md)

**11. Flat bind is `pair_width 2`, not 0.** A flat `{a,b,c}` is an *array*
literal; it becomes a `bind` (paired at width 2) only when coerced into a bind
slot. Older tables saying "flat literal → pair_width 0" are wrong. → [01 §8](01-types-and-values.md)

**12. Sub-64-bit `float` is rejected, not promoted.** `#stack[float, N<64]` errors
even for `0.0`, which makes `sizes::small_float` (32) unusable for floats. → [01 §2](01-types-and-values.md)

**13. `char` / `byte` / `i32` / `i64` / `f32` / `f64` / `double` are not
first-class.** They degrade to untyped passthrough: no coercion, no default, no
validation. → [01 §3](01-types-and-values.md)

**14. `#DEFINE` (uppercase) is a runtime no-op in the interpreter.** It's a
compiler/transpiler construct — entry point, passthrough, compile-time const —
not a runtime-substituted constant, and entirely distinct from `#define`. → [03 §6](03-scopes-and-req.md)

**15. `#scanp` / `#scanp_opt` are not module-gated.** The `def` gate is dead for
them, despite the docs filing `#scanp_opt` under `def`. → [04](04-callables.md) / [08](08-directives.md)

**16. A callee `&param` hint is ignored.** The call site alone decides ref vs
copy. → [04 §7](04-callables.md)

**17. Spellings, and things that aren't directives.** `#adress` has one `d`.
`#address` and `#memory` don't exist. `#require` and `#call` are not directives —
`call` is an object keyword. → [08](08-directives.md)

**18. `select` needs a `jump`; backward is `!jump`.** There is no `jump_back`. →
[09 §5](09-control-flow.md)

**19. Backend restrictions.** `#redefine` is interpreter-only (native lowers
statically). `#interrupt` is native/CCOS-only. The threading directives
(`#daemon` / `#killdaemon` / `#thread`) aren't in the native backend yet. →
[04](04-callables.md) / [08](08-directives.md)

### Previously fuzzy, now settled

**Bare heap literals in argument position are allowed — and ownerless, therefore
transient.** A bare literal (`cssc::outln("hi")`, a bare `[1,2,3]` argument) is a
legal transient: no owning slot, so it lives for the duration of the call and is
freed on return. It is *not* parse-rejected. To keep the value afterwards, copy
it into an owning slot with `&`. This falls straight out of the general ownership
rule ([02 — the owner rule](02-memory-and-ownership.md)); the LSP flags an
ownerless value passed to a *retaining* call as `TRANSIENT_LITERAL_IN_CALL_ARG`.

**Objects have no access control at all.** `public` / `private` is a sector-only
feature. Objects expose every member (`->`) and every label (`.`). Legacy
`secure !` markers on objects are decoration. → [05](05-objects.md) / [06](06-sectors.md)

---

## Conventions

- One topic, one numbered file, one row in the table above.
- Every rule is verified against R2 before it's written down. If it hasn't been
  run, it doesn't go in.
- Where R2 and intent disagree, document R2 and flag the conflict here rather
  than quietly writing the nicer version.
- Where a behavior is interpreter-only or native-only, say so in the chapter, not
  just here.

**Language:** this set is English, matching the fact sheet and the toolchain
notes. The previous set was German — say the word and it goes back.
