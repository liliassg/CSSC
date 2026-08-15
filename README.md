# CSSC Language Reference

**CSSC — Control Specified Source Compiling.** This is the authoritative,
modular reference for the CSSC language: precise rules, correct minimal examples,
and explicit callouts wherever historical docs were wrong. It is written against
the canonical implementation and verified there.

> **Canonical source of truth.** Where any prose disagrees with the
> implementation, the implementation wins. The reference implementation is
> `includecpp/core/cssl/cssl_cssc.py`. That file defines `CsscRuntime` **twice**;
> the **second** one (~line 13559, "R2") is what `cssc run` actually executes —
> the first (~line 4416, "R1") is dead/shadowed. Everything here is stated for
> **R2**. Maintainers editing behavior must edit R2 (R1 is a defensive relic).

---

## Read this in order (or jump to a topic)

| # | File | One line |
|---|---|---|
| 00 | **README** (this file) | Index, vision, toolchain, and the full doc↔impl conflict log. |
| 01 | [01-types-and-values.md](01-types-and-values.md) | Primitive types & sizes, `null`/`0x0`, literals, the `sizes` module, containers (array/vector/map/bind). |
| 02 | [02-memory-and-ownership.md](02-memory-and-ownership.md) | **Highest-stakes.** `#stack`/`#heap`/`#auto`, exact free-timing, `#delete`/`#delmember`/`#free`, the delete cascade, aliasing. |
| 03 | [03-scopes-and-req.md](03-scopes-and-req.md) | Isolation barriers vs transparent blocks, name resolution, `#req` (ref vs `&`snapshot), `#DEFINE`. |
| 04 | [04-callables.md](04-callables.md) | `#define`/`#cdefine`, parameters, call-site ref/copy, `mirror` vs `return`, variable-is-function duality. |
| 05 | [05-objects.md](05-objects.md) | `object` structure, `->` members, `.` labels, overloading, constructor params, `secure !` (inert in R2). |
| 06 | [06-sectors.md](06-sectors.md) | `sector` namespaces, `::` public/private enforcement, isolation, dependency injection, deferred init. |
| 07 | [07-modules.md](07-modules.md) | `#include`/`#load`/`#depend`/`#unload`, the `::` dispatch asymmetry, module search dirs. |
| 08 | [08-directives.md](08-directives.md) | Full `#…` directive reference table, grouped, with module gates and backend notes. |
| 09 | [09-control-flow.md](09-control-flow.md) | `if`/`for`/`while`, `select` + `jump` cursor iteration, `break`/`continue`. |
| 10 | [10-access-operators.md](10-access-operators.md) | The definitive `::` vs `->` vs `.` rules — the #1 source of mistakes. |

New topics should be added as their own numbered file so the reference grows
modularly; cross-link them into this table.

---

## The CSSC vision

CSSC is a small, hardware-near language designed around a few uncompromising
goals:

- **Performant — at least as fast as C.** Perf is a feature to be benchmarked,
  not assumed. Hot paths are offloaded to C++/native and the compiler applies
  aggressive dead-code elimination.
- **Everything RAW — no safety nets.** No garbage collector, no implicit bounds
  checks, no hidden copies, no automatic scope cleanup (except `#heap` at program
  end). You allocate in bits and you free explicitly. This is deliberate: on a
  microcontroller you want to know where every bit goes.
- **Tiny binaries, no bloat.** Aggressive DCE and a minimal runtime keep native
  output small.
- **One source, many backends.** The same `.cssc` runs on the interpreter and
  compiles to native host code and to embedded targets (ESP32/ESP8266/Arduino/
  Raspberry Pi), and can transpile (e.g. to Luau).
- **Deterministic.** Sizes, layout, and evaluation order are predictable.
  Determinism is what buys both efficiency *and* readability — you can reason
  about exactly what the machine will do.
- **Kernel-capable.** The RAW, deterministic model is meant to reach down to
  bare-metal / ISR-level code (`#interrupt`, GPIO, etc.).

The trade of this philosophy: the language will do exactly what you wrote,
including leak memory you didn't free. The rules in these docs are the contract
that makes that safe to rely on.

---

## Toolchain overview

| Command | What it is |
|---|---|
| `cssc run <file>` | **Interpreter** (stage-0, pure Python). The behavioral oracle — R2 is what runs here. |
| `cssc build <file> [-o out]` | **Native compiler.** Host target needs LLVM ≥ 17. Embedded targets via `--esp32` / `--esp8266` / `--arduino` / `--raspberry`; `--gcc` is the legacy host path. |
| `cssc native --target host` | Native build (LLVM ≥ 17). |
| `cssc analyze <file> --raw` / `cssc lsp diagnostics <file>` | **LSP / static analysis** (pure Python) — diagnostics, lints (e.g. `SELECT_WITHOUT_JUMP`). |
| `cssc convert <file> --luau` | Transpile to another backend. |
| `cssc install …` / `cssc module install …` | Build/distribute `.obj` packages and installable modules. |

Three implementations must agree on the semantics in these docs: the
**interpreter** (`cssc run`), the **native compiler** (`cssc build`), and the
**LSP** analyzer. Where a behavior is interpreter-only or native-only, the
relevant chapter says so.

---

## The rules people get wrong (quick reference)

If you internalise nothing else, internalise these — each links to its chapter.

- **`b = a` is not a universal live reference.** Scalars and strings are
  **value-copied**; only containers alias. Live cross-slot links come only from
  `#req` or argument passing. → [02 §8](02-memory-and-ownership.md)
- **`#delete` on a reference cascades up the *whole* chain** (not one level);
  ref-parameter *mutation* write-back is the single-level one. → [02 §5.1](02-memory-and-ownership.md)
- **`#heap` frees at program end**, not at block exit — except a **bare `{}`**
  block, which discards the heap it created at `}`. → [02 §3](02-memory-and-ownership.md)
- **Barriers vs windows.** `#define`/`{}`/object/label/sector hide outer names
  (import via `#req`); `if`/`for`/`while`/`select`/`else` see the enclosing scope.
  → [03](03-scopes-and-req.md)
- **The call site decides ref vs copy** (`f(x)` ref, `f(&x)` copy); a callee
  `&param` hint is ignored. → [04 §7](04-callables.md)
- **`::` vs `->` vs `.` are not interchangeable**, and `->` is not
  access-checked. → [10](10-access-operators.md)
- **Object privacy is inert in R2** — use a **sector** for enforced privacy.
  → [05 §7](05-objects.md) / [06](06-sectors.md)
- **`select` needs a `jump`** or the cursor never advances. → [09 §5](09-control-flow.md)
- **`float` is always 64-bit** — `#stack[float, N<64]` is rejected. → [01 §2](01-types-and-values.md)

---

## Doc ↔ impl conflict log (everything corrected here)

These are the places where earlier prose docs (and, for two of them, the
maintainer's own fact sheet) disagreed with R2. In every case the **R2 behavior
is documented as canonical**, per the precedence rule above.

### ⚠ Contradicts the maintainer's fact sheet / stated "critical facts" — please note

1. **`#delete` cascade depth is the OPPOSITE of the fact sheet.** The fact sheet
   (and the task brief) state: "`#delete` cascades exactly ONE caller level;
   assignment write-back cascades all levels." **R2 does the reverse:**
   `_delete_cross_frame` (line 17451) recurses the **entire** ref-link chain
   (cap 16 levels; its docstring documents the `p→q→y` N-level cascade), while
   ref-parameter **mutation** write-back on return is single-level. The
   "one-level delete" behavior is the **dead R1** (line 8710). Documented per R2
   in [02 §5.1](02-memory-and-ownership.md). *If the intended design is
   one-level delete, R2 needs changing — flagged for your decision.*

2. **Object access control (`secure !`, object `private:`) is INERT in R2.** The
   enforcement code exists but is gated on `_access_enabled`, which is initialised
   `False` and never set `True` anywhere. So `secure !` has no effect and a
   private object label is still callable (it does **not** return `0x0`). Legacy
   docs showing `c.secret() -> 0x0` describe intent, not behavior. Documented in
   [05 §7](05-objects.md). Use sectors for real privacy.

### Corrected from prose docs

3. **`b = a` aliasing.** Legacy §8.1/§8.4 claim plain assignment makes a live
   reference even for `int`/`string`. R2: scalars and strings are value-copied;
   only containers alias. → [02 §8](02-memory-and-ownership.md)

4. **`->` is not access-checked (the `::`/`->` asymmetry).** A private sector
   member is hidden from a `::` read but fully readable *and writable* through
   `->`. → [10](10-access-operators.md) / [06 §2](06-sectors.md)

5. **Sector `Sector::member = v` write persists.** `cssc-sectors.md` S12 says it
   is a silent no-op; R2 persists the write. (That doc describes the
   native/transembly "dead write" model.) → [06 §2](06-sectors.md)

6. **Sector `<A: B>` is variable injection, not a typed constructor param.** For
   sectors, `<outerVar: localName>` injects the outer variable under a local name.
   Typed constructor params (`<int: width>`) are an **object**-only feature. Legacy
   §6.3 and a stale docstring are wrong. → [06 §4](06-sectors.md)

7. **`free {}` / `#free` are optional and unenforced.** Docs call them
   "mandatory"; R2 has no leak check and no error if you forget. (Still best
   practice; `.obj` `#free` matters for compiled builds.) → [06 §6](06-sectors.md)

8. **Builtin-module `#free` is a no-op;** real module teardown is `#unload`
   (`#load`/`#depend`). Docs imply every `#include` needs a `#free`. → [07 §6](07-modules.md)

9. **`alias::member` missing-member asymmetry.** A missing **builtin-module
   method call** is a hard error; a private/missing **sector** member is a silent
   `null`. → [07 §3](07-modules.md) / [10](10-access-operators.md)

10. **Container literals `{…}` and `[…]` are both native lists** at runtime; the
    typed slot (not the bracket) decides when you get `CsscArray`/`CsscVector`.
    → [01 §7](01-types-and-values.md)

11. **Flat bind is `pair_width 2`, not 0.** A flat `{a,b,c}` is an *array*
    literal; it becomes a `bind` (paired at width 2) only on coercion into a bind
    slot. Older tables saying "flat literal → pair_width 0" are wrong. → [01 §8](01-types-and-values.md)

12. **`float` sub-64-bit is rejected, not promoted.** `#stack[float, N<64]`
    errors even for `0.0`. `sizes::small_float` (32) is unusable for floats. →
    [01 §2](01-types-and-values.md)

13. **`char`/`byte`/`i32`/`i64`/`f32`/`f64`/`double` are not first-class** — they
    degrade to untyped passthrough (no coercion/default/validation). → [01 §3](01-types-and-values.md)

14. **`#DEFINE` (uppercase) is a runtime no-op in the interpreter** — a
    compiler/transpiler construct (entry-point / passthrough / compile-time
    const), not a runtime-substituted constant. Distinct from `#define`. →
    [03 §6](03-scopes-and-req.md)

15. **`#scanp` / `#scanp_opt` are not actually module-gated in R2** (the `def`
    gate is dead for them), despite the docs grouping `#scanp_opt` under `def`. →
    [04](04-callables.md) / [08](08-directives.md)

16. **Callee `&param` hint is ignored;** the call site alone decides ref vs copy.
    → [04 §7](04-callables.md)

17. **Spellings & non-directives.** `#adress` has **one `d`** — `#address` and
    `#memory` do not exist. `#require` and `#call` are not directives (`call` is
    an object keyword). → [08](08-directives.md)

18. **`select` needs a `jump`; backward is `!jump`** (there is no `jump_back`).
    → [09 §5](09-control-flow.md)

19. **Backend restrictions:** `#redefine` is interpreter-only (native lowers
    statically); `#interrupt` is native/CCOS-only; threading directives
    (`#daemon`/`#killdaemon`/`#thread`) are not in the native backend yet. →
    [04](04-callables.md) / [08](08-directives.md)

### Resolved semantics (previously fuzzy — now confirmed with the maintainer)

- **Bare heap literals in argument position are ALLOWED — but ownerless, so
  transient.** A bare literal (`cssc::outln("hi")`, a bare `[1,2,3]` arg) is a
  legal *transient*: it has no owning slot, so it lives only for that call and is
  freed when the call returns. It is **not** parse-rejected. To keep such a value
  past the call, copy it into an owning slot with `&`. This is the general
  ownership rule (see [02 — the owner rule](02-memory-and-ownership.md)); the LSP
  flags an ownerless value passed to a *retaining* call as
  `TRANSIENT_LITERAL_IN_CALL_ARG`.
- **Objects have no access control.** `public`/`private` is a **sector**-only
  feature; objects expose every member (`->`) and label (`.`). Legacy `secure !`
  object markers are inert — use a sector for privacy. See
  [05](05-objects.md) / [06](06-sectors.md).

### Style note

- **Written in English.** The prior doc set was German; this new set is English
  to match the fact sheet, the toolchain notes, and this task. Say the word if
  you want it in German.
