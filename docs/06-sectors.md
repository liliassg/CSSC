# 06 — Sectors

A `sector` is CSSC's **namespace with enforced privacy**. Unlike objects (whose
privacy is inert in R2 — see [05-objects §7](05-objects.md)), a sector actually
gates `private:` members: reading one from outside via `::` returns `0x0`.
Sectors are also **isolated** — a sector body runs in its own variable space and
cannot see top-level globals unless you inject them.

---

## 1. Structure

```cssc
sector Engine {
private:
    #stack[int, 32] Engine->fps = 60;
public:
    #stack[string, 128] Engine->title = "MyEngine";
    #define(Engine->start) {
        cssc::outln("Engine starting");
    }
} free {
    #delete[Engine->fps];
    #delete[Engine->title];
};
```

Header grammar:

```
sector NAME <injection-list>? ?reserveLabel? { private: … public: … } free { … }?
```

- **`private:` / `public:`** sections split the members. **Default is `private`**
  if you write members before any section label.
- Members are declared and accessed **internally** with `->` (`Engine->fps`), and
  reached **externally** with `::` (`Engine::title`, `Engine::start()`).
- **`free { }` is optional** in R2 (see §6) — though you should still write it to
  release members.

---

## 2. Public / private (`::` enforced; `->` is the escape hatch)

- **`Sector::member`** — external access is **access-checked**: a `public:`
  member is returned; a `private:` member read returns `0x0` (null), not an error.
- **`Sector->member`** — **not** access-checked. A private member is fully
  readable *and writable* through `->`. This is the deliberate `::` / `->`
  asymmetry (see [10-access-operators](10-access-operators.md)).
- A **`Sector::member = v` write** is *not* access-checked and **persists** in
  the interpreter.

```cssc
cssc::outln(Engine::title);   // public -> the value
cssc::outln(Engine::fps);     // private via :: -> 0x0
cssc::outln(Engine->fps);     // private via -> -> 60 (not gated!)
```

> **Impl-canonical note.** Legacy `cssc-sectors.md` says an external
> `Sector::member = v` write is a silent no-op that does not persist. In R2 the
> interpreter **does persist** it. (That doc describes the native/transembly
> "dead write" model; the interpreter is a live write.)

---

## 3. Isolation

A sector body is a barrier with its **own variable space**. During construction
the runtime swaps `_variables`/`_stack_vars`/… out for a fresh set, runs the body,
then restores the outer set — so:

- Top-level globals are **not** visible inside the sector unless injected (§4).
- A bare, unknown identifier inside a sector resolves to `0x0` — there is no
  silent fallback to a same-named global.
- Inside a running sector method, a `ns::func(...)` call is allowed only when `ns`
  is `cssc`, the sector itself, one of its members, or an injected dependency —
  otherwise you get a **`Sector-Isolation`** error.

```cssc
#stack[int, 32] globalX = 99;

sector Iso {
public:
    #define(Iso->show) {
        cssc::outln(globalX);   // -> 0x0  (globalX is NOT visible; not injected)
    }
} free {};
```

To use `globalX`, inject it (next section).

---

## 4. Dependency injection / generics (`<…>`)

The `<…>` header list **injects outer variables** into the sector's scope. Each
entry is one of:

| Form | Meaning |
|---|---|
| `<name>` | Inject outer variable `name` by **reference** (zero-copy, shared). |
| `<&name>` | Inject outer variable `name` as a **deep-copy snapshot**. |
| `<outerVar: localName>` | Inject outer variable `outerVar` under the local name `localName` (ref by default; `&`/`*` modifiers allowed on either side). |
| `<*name>` | **Deprecated** ref spelling; identical to bare `<name>`. |

```cssc
#stack[int, 32] globalConfig = 42;

sector App<globalConfig> {          // inject by reference (shared)
    #define(App->run) {
        cssc::outln(globalConfig);  // -> 42
    }
} free {};

sector Snapshot<&globalConfig> { … } free {};   // inject an independent copy
sector Aliased<globalConfig: cfg> { … } free {}; // inject under the name 'cfg'
```

> **Impl-canonical note (important).** For **sectors**, `<A: B>` means *inject
> outer variable `A` under local name `B`* — it is **not** a typed constructor
> parameter. Legacy docs (and a stale docstring) call `<type: name>` a "sector
> constructor parameter"; that is wrong. Typed constructor params (`<int: width>`)
> are an **object** feature (see [05-objects §4](05-objects.md)), not sectors.

---

## 5. Deferred initialization (`?reserve` + `#reserve`)

A sector marked with `?label` in its header is **not** constructed at its
definition point. It is stashed, and constructed later by `#reserve[label]`.

```cssc
sector Config ?app {
    #define(Config->run) { cssc::outln("running"); }
} free {};

#reserve[app];      // NOW the sector is constructed
app::run();
#free[app];
```

Use this when a sector must be built at a controlled moment (after some setup)
rather than where it textually appears.

---

## 6. Teardown (`free { }` + `#free`)

- `#free[Sector]` runs the sector's `free { }` block and drops it.
- `#unload[alias]` is the analogous teardown for a *loaded module* and cascades
  to that module's child sectors (see [07-modules](07-modules.md)).

```cssc
#free[Engine];
```

> **Impl-canonical note.** `free { }` is **optional and unenforced** in R2. The
> parser allows a sector with no `free` block, `run_free` is a no-op when the
> block is empty, and **nothing errors if you never `#free` a sector** — there is
> no leak check. Legacy framing that calls `free`/`#free` "mandatory" describes
> good practice, not a runtime rule. Write and call them anyway to avoid leaks in
> compiled builds.

---

## 7. Nested and self-referencing sectors

An inner sector can inject its enclosing sector to reference it:

```cssc
sector Outer {
    sector Inner<Outer> {          // Inner captures Outer by reference
        // Inner can reach Outer's injected members
    } free {};
} free {};
```

During construction a live placeholder for the parent shares the same variable
space, so inner sectors see the parent as a real reference (v6 default;
`<*Outer>` is the deprecated spelling).

---

## Common mistakes / impl-canonical notes

- **Sectors are the real privacy tool.** `::` reads enforce `private:`; objects do
  not enforce anything in R2.
- **`->` bypasses sector privacy** (read and write). Only `::` reads are gated.
- **`Sector::member = v` persists** in the interpreter — it is not a no-op.
- **`<A: B>` on a sector injects a variable, not a typed param.** Typed
  constructor params are objects-only.
- **No top-level global fallback** inside a sector — inject with `<…>` or the name
  is `0x0`.
- **`free`/`#free` are optional/unenforced** — no leak error — but you should
  still use them.

## See also

- [10-access-operators](10-access-operators.md) — the `::`/`->`/`.` rules and the asymmetry.
- [03-scopes-and-req](03-scopes-and-req.md) — sector body as an isolation barrier.
- [07-modules](07-modules.md) — modules vs sectors, `::` dispatch, `#free`/`#unload`.
- [05-objects](05-objects.md) — objects (typed constructor params; inert privacy).
