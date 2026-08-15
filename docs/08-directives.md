# 08 — Directive Reference

The complete list of `#…` directives in the canonical R2 runtime, grouped by
purpose. This is the single source of truth for each directive's spelling and
one-line meaning; the deeper semantics live in the linked chapters.

## How directives are written

- Most directives take arguments in **brackets** `#name[…]` or **parens**
  `#name(…)`. In R2 the lexer captures both into one argument field, so the
  `[ ]` vs `( )` choice is largely a **documentation convention** — this reference
  uses the conventional punctuation for each. (`#include(...)` is the one that is
  genuinely special-cased.)
- A directive may take a **trailing name** it declares/targets:
  `#stack[int, 32] x = 5;`.
- A `&` / `*` prefix on the trailing name is meaningful for `#req`/`#scanp`
  (ref/copy/deprecated) — see [03](03-scopes-and-req.md) / [04](04-callables.md).

**Module gate** column: which `#include('…')` module must be loaded first.
**Backend** notes interpreter-only vs native where known from the runtime; "—"
means no special restriction observed in this file.

---

## Memory

| Directive | Syntax | Semantics | Gate | Backend |
|---|---|---|---|---|
| `#stack` | `#stack[type, bits] name = init;` | Fixed stack buffer. **Default 256 bits.** Overflow errors. Hex name -> hex-var store. | — | — |
| `#heap` | `#heap[type, bits] name = init;` | Heap buffer. **Default 1024 bits.** Auto-freed at **program end**. | — | — |
| `#auto` | `#auto[type] name = init;` | Auto-sized buffer. **Min 32 bytes**, grows. Manual `#delete`. | — | — |
| `#delete` | `#delete[name]` / `#delete[0xADDR]` / `#delete[Sec->m]` | Free a slot; dtor cascade over members; **multi-level ref-chain cascade** (cap 16). | — | — |
| `#delmember` | `#delmember[c]` / `#delmember[c[i]]` | Soft-wipe contents; keep size/capacity. Idempotent, null-safe. | — | — |
| `#free` | `#free[sector]` / `#free[obj]` / `#free[alias]` / `#free[0xADDR]` | Run `free { }` then drop a sector/object/loaded-module. Builtin module -> no-op. | — | — |
| `#reallocate` | `#reallocate[var, type, stack\|heap, size?] newvar;` | True region move; **type-strict**; default grow `+32` bits. | — | — |
| `#resize` | `#resize[var, ±bits];` | Grow/shrink an existing alloc; follows ref chain. | — | — |
| `#reserve` | `#reserve[label];` / `#reserve[mod.label];` | Construct a deferred `sector … ?label`. | — | — |
| `#set` | `#set[0xADDR, bits] = value;` | Write a coerced value at a known address (bit-checked). | — | interp (raw mem) |
| `#peekstack` / `#peekheap` | `#peekstack[src, type, index, amount] name;` | Slice a collection into a new stack/heap var. | — | — |
| `#cast` | `#cast[source, target] result;` | Coerce `source` into an existing `#heap` target. | — | — |
| `#adress` | `#adress[var] name;` (get) · `#adress[var] = 0xABC;` (alias) · `#adress[var]` (expr) | Address introspection. Missing var -> `0x0`. **One `d`.** | — | alias form interp-only |

> **Not directives:** `#address` and `#memory` do **not** exist (`#memory` is
> explicitly rejected). The only spelling is `#adress`.

---

## Callables

| Directive | Syntax | Semantics | Gate |
|---|---|---|---|
| `#define` | `#define(name) { … }` | Bind a no-param callback to a slot. | — |
| `#cdefine` | `#cdefine(func, p1, p2) { … }` | Callback with named parameters. | **def** |
| `#redefine` | `#redefine(fn) { … }` · `#redefine(fn) +<pos> { … }` | Overwrite / inject into a function body. **Interpreter-only** (native lowers statically). | — |
| `#fvar` | `#fvar(type) name;` | Declare a typed function-variable (no init). | **def** |
| `#param` | `#param(type) name;` | Declare a typed parameter (no init; filled by `#scanp`). | **def** |
| `#scanp` | `#scanp(src, type, pos) name;` · `… &name;` · `… name = default;` | Read a positional call arg. **Ref/copy decided by the call site**; missing -> null. | — |
| `#scanp_opt` | `#scanp_opt(src, type, pos) name;` | Like `#scanp`, but a missing arg -> null silently. | (docs say def; **gate is dead in R2**) |
| `#qvar` | `#qvar(type, expr) name;` | Materialise `expr` into a typed local. | **def** |
| `#daemon` | `#daemon[funcVar];` | Run a `#define` func repeatedly in a background thread. | **asyncthreads** |
| `#killdaemon` | `#killdaemon[funcVar];` | Cooperatively stop a daemon. | **asyncthreads** |
| `#thread` | `#thread[type, bits] name = init;` | Declare a thread-callable var. | **asyncthreads** |
| `#await` | `#await[handle] result;` | Join a daemon, capture its result. | **asyncthreads** |
| `#raii` | `#raii 0xADDR method(args);` / `#raii name method(args);` | Call a method on a hex/named scope (no brackets on the directive). | — |
| `#interrupt` | `#interrupt(name) { … }` | Hardware ISR. **Native (CCOS) only**; interpreter registers but never auto-invokes. | — |

> **`#call` is not a directive.** `call` is a keyword used in objects
> (`call label<args> capture;` — see [05-objects](05-objects.md)). There is no
> `#call`.

---

## Scope & Modules

| Directive | Syntax | Semantics | Backend |
|---|---|---|---|
| `#include` | `#include("mod")` / `#include("mod") alias;` | Load a builtin module. Unknown -> error. | — |
| `#load` | `#load["path.cssc"] alias;` | Load an external `.cssc` file as a child-runtime module (globals -> public). | interp (child runtime) |
| `#depend` | `#depend["path.obj"] alias;` | Load an isolated `.obj` package; exposes `alias::sector::member`. | — |
| `#unload` | `#unload[alias];` | Unload a loaded module, running child sectors' `free { }`. | — |
| `#req` | `#req[X] Y;` (ref) · `#req[X] &Y;` (copy) · `#req[Sec->m] Y;` | Import an outer/sector var into a barrier. **Ref by default**; `&` = deep-copy snapshot. | — |
| `#REQUIRE` | `#REQUIRE["path"] var;` | Load a resource by extension (`.dll/.ini/.csl/.cssl`). **Uppercase — not `#req`.** | — |
| `#tlisten` | `#tlisten[var] { body }` | Run `body` if the watched var is non-null. | interp |

> **`#require` does not exist.** Only `#req`, `#REQUIRE`, `#include`, `#load`,
> `#depend`, `#unload` are real.

---

## Introspection

| Directive | Syntax | Semantics |
|---|---|---|
| `#size` | `#size[var] out;` | **Used** size in bits. |
| `#capacity` | `#capacity[var] out;` | **Allocated** capacity in bits (follows ref chain). |
| `#exists` | `#exists[0xADDR] out;` | 1/0 — is this address a known allocation? |
| `#reflect` | `#reflect[address] out;` | Resolve an address back to its value. |
| `#adress` | (see Memory) | Address of a slot; `0x0` if unbound. |
| `#iterator` | `#iterator[type, source] name;` | Create an STL-style iterator over a container. |

---

## IO & Diagnostics

| Directive | Syntax | Semantics | Gate |
|---|---|---|---|
| `#stdout` | `#stdout(text)` | Write to the stdout module + output buffer. | **stdout** |
| `#debug` | `#debug(msg);` | Append to `dev::stdout` always; print to stderr only with `--debug`. | — (from `devdebug`) |
| `#trace` | `#trace(funcName);` | Log each call of a function (only under `--debug`). | — (from `devdebug`) |
| `#catch` | `#catch (callable) ?caller { body }` | Catch a runtime error; bind the message to `?caller`. | — (from `stdgrace`) |
| `#panic` | `#panic("message");` | Throw an artificial runtime error. | — |
| `#sysarg` | `#sysarg[type, index] var;` | CLI arg -> stack var (needs `#delete`). | **sys** |
| `#sysout` | `#sysout(expr);` | Return a value to the `cssc.run()` host caller. | — |
| `#clock` | `#clock[ms];` | Sleep `ms` milliseconds. | — |
| `#REQUIRE` | (see Scope & Modules) | Resource load. | — |
| `#OUTPUT` | `#OUTPUT["path"]` | Set the output path. | — |
| `#EXIT` | `#EXIT[code]` | Set exit code and stop. | — |
| `#DEFINE` | `#DEFINE name;` · `#DEFINE __main__ '__main__';` · `#DEFINE name <expr>;` | **Compiler/transpiler** construct (entry-point / passthrough / compile-time const). **Runtime no-op in the interpreter.** Distinct from lowercase `#define`. | transpiler/native |

---

## Types (typed-declaration directives)

| Directive | Syntax | Gate |
|---|---|---|
| `#VARIABLE` | `#VARIABLE[type] name = value;` | — |
| `#string` | `#string[bits] name = init;` | **string** |
| `#int` | `#int[bits] name = init;` | **int** |
| `#array` | `#array[type, size] name = init;` | **array** |
| `#vector` | `#vector[type, bits] name = init;` | **vector** |
| `#map` | `#map[keytype, valtype, bits] name = init;` | **map** |
| `#matrix` | `#matrix[width, height] name = fill;` | **matrix** |

> For containers, the second `#stack`/`#heap` argument is an **element capacity**,
> not a scalar bit-limit (see [01-types-and-values §6](01-types-and-values.md)).
>
> **Known bug:** the `#array[type, size]` directive form passes two args to a
> one-arg constructor and raises `TypeError` in R2. Use an `array<T>` typed
> declaration or an `{…}` literal instead.

---

## Hardware / Peripherals

All are `#include`-documented but **not** runtime-gated in R2 (the helpers
construct directly). See the toolchain docs for target mapping.

| Directive | Syntax | Meaning |
|---|---|---|
| `#pin` | `#pin[N] var;` | GPIO line |
| `#i2c` | `#i2c[bus, sda, scl] var;` | I2C master |
| `#spi` | `#spi[bus, sck, miso, mosi] var;` | SPI master |
| `#uart` | `#uart[bus, tx, rx] var;` | UART/serial |
| `#adc` | `#adc[pin] var;` | ADC input |
| `#pwm` | `#pwm[pin, freq, bits] var;` | PWM output |
| `#timer` | `#timer[slot, hz] var;` | Periodic timer |
| `#tft` | `#tft[ctrl, w, h] var;` | TFT/OLED panel |
| `#oled` | `#oled[w, h] var;` | Sugar for `#tft[ssd1306, w, h]` |
| `#video` | `#video[w, h, fps] var;` | Video context (gate **video**) |
| `#framebuffer` | `#framebuffer[w, h] var;` | Pixel buffer (gate **video**) |
| `#console` | `#console[w, h] var;` | Native console window |
| `#get` / `#post` / `#send` | `#get[url] var;` · `#post[url] var = body;` · `#send[url] body;` | HTTP (from `network.http`) |

---

## Directives that do NOT exist (common false friends)

| Looks plausible | Reality |
|---|---|
| `#require` | Not a directive. Use `#req` (var import), `#include`/`#load`/`#depend` (modules), `#REQUIRE` (resources). |
| `#address` | Not a directive. The spelling is `#adress` (one `d`). |
| `#memory` | Not a directive (explicitly rejected). |
| `#call` | Not a directive. `call` is an object keyword. |

## See also

- [02-memory-and-ownership](02-memory-and-ownership.md) — memory directives in depth.
- [04-callables](04-callables.md) — `#define`/`#scanp`/`mirror` semantics.
- [03-scopes-and-req](03-scopes-and-req.md) — `#req`, `#DEFINE`.
- [07-modules](07-modules.md) — `#include`/`#load`/`#depend`/`#unload`/`#REQUIRE`.
