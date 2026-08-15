# 07 — Modules

A module is a reusable namespace reached with `::`. CSSC has three kinds:

1. **Builtin modules** — loaded with `#include('name')`, drawn from a fixed
   in-runtime registry (`video`, `def`, `sizes`, `os`, …).
2. **Loaded CSSC files** — `#load["file.cssc"] alias;` runs another `.cssc` file
   as a child runtime and exposes its globals.
3. **`.obj` packages** — `#depend["pkg.obj"] alias;` loads a prebuilt package.

---

## 1. `#include` — builtin modules

```cssc
#include('video') vid;      // load 'video', alias it 'vid'
#include('os') os;
#include('def');            // no alias: the module name is the key
```

- `#include('name') alias;` loads a **builtin** module and binds `alias`.
- Without an alias, the module name itself is the storage key.
- Unknown module name -> a runtime error ("Unknown module").
- The `'name'` may use single or double quotes.

> **Teardown reality.** Legacy docs say "every `#include` needs a `#free[alias]`".
> For a **builtin** module, `#free` is a **no-op** in R2 (there is nothing to
> release at runtime), so forgetting it in the interpreter is harmless. It is only
> `#load`/`#depend` modules (and native/`.obj` builds) where teardown actually
> matters — see §6.

---

## 2. Selected builtin modules

| Module | What it provides |
|---|---|
| `def` | Extended callables: `#cdefine`, `#fvar`, `#param`, `#qvar`, `#scanp_opt` (see [04-callables](04-callables.md)) |
| `sizes` | Recommended bit-size constants: `sz::normal_int`, … (see [01-types-and-values §6](01-types-and-values.md)) |
| `sys` | CLI args: `sys::args`, `sys::argc`, `sys::arg(i)`, … |
| `stdio`, `cssc.io` | File I/O |
| `cssc.math` | Math (trig, logs) |
| `console` / `sys.console` | Native console window + sync |
| `devdebug` | `#debug`, `#trace`, `dev::stdout` |
| `stdgrace` | Graceful errors: `grace::catch`, `#catch` |
| `asyncthreads` | `#daemon`, `#killdaemon`, `#thread`, `#await` |
| `video` (+ `video.sprite`, `.tilemap`, `.font`) | Native windowing + 2-D graphics |
| `keyboard`, `mouse`, `sound` | Input and audio |
| `gipeo` | GPIO/I2C/SPI/UART/ADC/PWM/timer for embedded targets |
| `tft` | TFT/OLED displays |
| `network.http` | HTTP/HTTPS client |
| `openai` | OpenAI chat/embeddings |
| `matrix`, `serialcommunication`, `os` | Pixel matrix, IPC, OS access |

(The full registry is larger; this table covers the common ones. Module-gated
directives are listed per-group in [08-directives](08-directives.md).)

---

## 3. `alias::member` dispatch — the missing-member asymmetry

How a missing member behaves **depends on the target kind**. This trips people up,
so it is worth stating exactly (see also [10-access-operators](10-access-operators.md)):

| Target | `alias::member` (read) | `alias::method(args)` (call) |
|---|---|---|
| **builtin module** | missing property -> `null` | **missing method -> runtime ERROR** `"Module 'alias' has no function 'method'"` |
| **sector** | private/missing -> `0x0` (null) | private/missing -> `0x0` (null) |
| **loaded module / `.obj`** | missing -> `null` | resolves against the file's public members |

> **Impl-canonical note.** The load-bearing asymmetry: calling a **missing builtin
> module function** is a hard error, but reaching a **private sector member** is a
> silent `null`. Do not rely on a `null` to tell you a builtin-module call was
> mistyped — it throws instead.

A **loaded CSSC file** (`#load`) exposes **all** of its globals as **public**
members — loaded-file modules have no private members.

---

## 4. `#load` — run another `.cssc` file as a module

```cssc
#load["helpers.cssc"] hlp;
hlp::doThing();
#unload[hlp];
```

- Parses and runs `helpers.cssc` in a child runtime, wrapped as a module.
- Every global in that file becomes a **public** member of `hlp`.
- Path resolution: see §8.

---

## 5. `#depend` — load a `.obj` package

A `.obj` is a self-contained, distributable CSSC package (a compiled DLL plus
optional source/assets). See the packaging guide for building them
(`cssc install …`).

```cssc
#depend['./math-helpers.obj'] mh;
#stack[int, 32] x = mh::mathlib::square(7);   // nested: alias::sector::func
cssc::outln(x);
#delete[x];
#free[mh];      // required for .obj — the loader holds the package open
```

- `#depend['path.obj'] alias;` loads the package and exposes its sectors as
  `alias::sector::member`.
- The first `::` access into a `#depend`'d package triggers a one-time branded
  watermark.
- **`#free[alias]` is required for `.obj`** — the package/DLL stays open until you
  free it (a real leak in compiled builds if omitted).

---

## 6. Teardown: `#unload` vs `#free`

| Directive | Frees what |
|---|---|
| `#unload[alias]` | Unloads a **loaded module** (`#load`/`#depend`), running each child sector's `free { }`, then removes it. The primary "free a loaded module" path. |
| `#free[alias]` | Runs `run_free()` on a sector / object / loaded module (cascading to child sectors). For a **builtin** `#include` module it is a **no-op**; on anything unexpected it errors. |

Rule of thumb: `#unload` for `#load`/`#depend` modules, `#free` for sectors,
objects, and `.obj` aliases. For a builtin `#include` module, teardown is a no-op
in the interpreter (but keep `#free` for portability to native builds).

Teardown is **not enforced** — nothing errors if you forget (same as sectors,
[06-sectors §6](06-sectors.md)) — but forgetting `#free` on a `.obj` leaks in
compiled builds.

---

## 7. `#REQUIRE` — resource loading (NOT `#req`)

`#REQUIRE` (uppercase) is unrelated to `#req` ([03-scopes-and-req](03-scopes-and-req.md))
and unrelated to modules-by-name. It loads an external **resource** by path,
auto-detecting the kind from the extension (`.dll`, `.ini`, `.csl`, `.cssl`).

```cssc
#REQUIRE["plugin.dll"] plug;
```

> Do not confuse the three: `#req` = import a variable across a barrier;
> `#REQUIRE` = load a resource file; `#include`/`#load`/`#depend` = load modules.
> There is **no** `#require` directive at all.

---

## 8. Module search directories

- **Builtin `#include` modules** come from a hard-coded in-runtime registry — they
  are **not** searched on the filesystem.
- **`#load` / file paths** resolve in order: absolute path -> relative to the
  running script's directory -> each configured search path -> the active CSSC
  version's installed-module directory (`cssc_env.modules_dir()`, populated by
  `cssc module install`).
- **`#depend` `.obj`** resolves in order: literal/absolute -> current working
  directory -> script directory -> `%APPDATA%/CSSC/<version>/objects/` (the
  per-user installed-package store).

A `cssc.cproject` file can centralise the module directory so `#depend['./x.obj']`
finds packages without hard-coded paths.

---

## Common mistakes / impl-canonical notes

- **There is no `#require`.** Use `#include`/`#load`/`#depend` for modules, `#req`
  for variable imports, `#REQUIRE` for resource files.
- **Builtin `#free` is a no-op**, but `.obj` `#free` is required (holds the package
  open).
- **Missing builtin-module call errors; missing sector member is null.** Don't
  conflate the two.
- **`#load` files expose everything as public** — no private members in a
  loaded-file module.

## See also

- [10-access-operators](10-access-operators.md) — `::` dispatch and the missing-member asymmetry.
- [06-sectors](06-sectors.md) — sectors vs modules; `#reserve`/`#free`.
- [08-directives](08-directives.md) — full syntax for `#include`/`#load`/`#depend`/`#unload`/`#REQUIRE`.
- [04-callables](04-callables.md) — the `def` module directives.
