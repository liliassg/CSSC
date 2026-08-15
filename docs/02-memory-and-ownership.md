# 02 — Memory & Ownership

> **This is the highest-stakes chapter in the whole set.** Almost every "CSSC did
> something I didn't expect" bug is a misread of one of the rules below. Read it
> whole. Where a legacy doc says something different, the callouts say so
> explicitly — the canonical implementation (`cssl_cssc.py`, runtime **R2**) wins.

CSSC has **no garbage collector and no hidden copies**. You allocate, you free.
The only automatic cleanup is `#heap` at program end (and barrier-scoped
discard, below). Everything else leaks unless you `#delete` / `#free` it. This is
by design — CSSC is RAW and deterministic (see [README](README.md)).

> **The one rule everything else follows from: a value survives only while a slot
> owns it.** A value with **no owner** — a bare heap literal (`"hi"`, `[1, 2, 3]`),
> a transient call argument, a borrowed `select` cursor (`?i`) — is **transient**:
> it lives for the current call/expression and is freed the instant that returns.
> Bare literals are perfectly legal as *transient* arguments (`cssc::outln("hi")`
> works). But to **keep** such a value you must **copy it into an owning slot**
> with `&` — give it an owner, or it dies. This single rule is why references-are-
> default (you hold the real thing), why `#delete` on a reference frees the
> referent (§5), and why a `select` cursor must be copied to outlive its loop
> ([09 §5](09-control-flow.md)). The LSP flags an ownerless value handed to a
> call that would retain it as `TRANSIENT_LITERAL_IN_CALL_ARG`.

---

## 1. The three allocation regions

Every declared variable lives in exactly one region. The region is chosen by the
directive that declares it.

| Directive | Syntax | Default capacity | Freed when? |
|---|---|---|---|
| `#stack` | `#stack[type, bits] name = init;` | **256 bits** | **Only** by manual `#delete[name]`. Leaks otherwise. |
| `#heap` | `#heap[type, bits] name = init;` | **1024 bits** | Auto-freed at **program end** — *or* earlier by optional `#delete`, *or* at a barrier's `}` if declared inside one (see §3). |
| `#auto` | `#auto[type] name = init;` | **min 32 bytes**, grows on demand | **Only** by manual `#delete[name]`. Leaks otherwise. |

The `bits` argument is a **capacity in bits**, not bytes and not element count.
`#stack[int, 32] x = 5;` reserves 32 bits. Writing a value that does not fit the
capacity is a hard runtime error, not silent wraparound.

```cssc
#stack[string, 256] name = "Hello";   // 256-bit buffer, must #delete
#heap[vector<int>, 1024] data = [1, 2, 3];  // auto-freed at program end
#auto[int] counter = 0;               // grows as needed, must #delete

#delete[name];
#delete[counter];
```

`float` has a hard floor: `#stack[float, N]` with `N < 64` is **rejected as a hard
error** (at declaration in the interpreter, and by the native/LSP path) because
`float` is always 64-bit — it is not rounded up. Minimum spec is
`#stack[float, 64] x = 3.14;`. See [01-types-and-values §2](01-types-and-values.md).

> **Embedded framing.** Bit-exact allocation is deliberate: on a microcontroller
> you want to *know* where every bit goes. `#auto` is the pragmatic escape hatch
> for host scripts where bit-accounting is noise.

---

## 2. `#stack` vs `#heap` vs `#auto` — choosing

- **`#stack`** — fixed capacity, you own the lifetime end-to-end. Default for
  locals and members you will explicitly `#delete`.
- **`#heap`** — larger default capacity, survives ordinary scope exit, and the
  runtime guarantees it is gone at program end even if you forget. Use for
  long-lived / large data. **Note the barrier exception in §3.**
- **`#auto`** — no `bits` argument; the buffer auto-sizes. Convenient, but you
  still must `#delete` it.

---

## 3. Exact free-timing (the rule people get wrong)

`#heap` is **not** freed at ordinary scope exit. It is freed at **program end**.
Ordinary control-flow blocks (`if`, `else`, `for`, `while`, `select`) do **not**
free heap allocations declared inside them.

Two things are distinct here and R2 treats them separately: **name visibility**
(which the barrier scopes) and **buffer lifetime** (which mostly follows the
region rule). Precisely, in R2:

- **The bare `{ … }` block is a scoped heap arena.** It installs a fresh heap
  store for its body and discards it at the closing `}`. `#heap` allocations
  declared directly inside a bare block die at that `}`.
- **`#define` / `#cdefine` / label bodies restore *name bindings* at `}`** (so
  their locals stop being visible), but they do **not** auto-free the underlying
  `#stack`/`#heap`/`#auto` buffers on return. Those follow the normal region
  rule: `#stack`/`#auto` must be `#delete`d (or they leak); `#heap` lives until
  program end. This is exactly why every `#define` example that allocates a local
  also `#delete`s it.
- **Object/sector member** allocations are transferred into the object/sector and
  released by `#free` (see [05-objects](05-objects.md) / [06-sectors](06-sectors.md)).

(See [03-scopes-and-req](03-scopes-and-req.md) for the full barrier vs
non-barrier list — that chapter is about *name visibility*; this section is about
*when the buffer dies*.)

```cssc
#heap[vector<int>, 1024] g = [];   // top level: lives until program end

if (cond) {
    #heap[vector<int>, 1024] a = []; // if is NOT a barrier -> 'a' survives
}                                    // ...the block, freed only at program end

{
    #heap[vector<int>, 1024] b = []; // bare {} is a scoped heap arena
}                                    // -> 'b' discarded here, at the }
```

So the mental model is: **the bare `{}` block auto-discards the heap it created;
everything else follows its region rule (stack/auto manual, heap program-end),
and a barrier's `}` only takes away *name visibility*.**

> **Common mistake.** "Heap is freed when the block ends, like a scoped C++
> object." Only the **bare `{}`** arena does that. `if`/`for`/`while`/`select`/
> `else` bodies do not free their heap (it dies at program end), and a `#define`
> body does not free its stack/auto buffers on return — you must `#delete` them.

---

## 4. Allocation names, including hex-keyed variables

A variable name is usually an identifier. It can instead be a **hex literal**,
which places the variable in a global hex-keyed store (uint64 key lookup instead
of string lookup). This is a performance/embedded convenience.

```cssc
#stack[int, 32] 0x0AA = 42;
cssc::outln(0x0AA);     // -> 42   (resolved as a variable lookup)
#delete[0x0AA];
```

- The *same* hex literal used in an arithmetic expression stays an ordinary
  integer constant **if no variable with that key exists**.
- Hex-keyed variables are checked *before* raw memory addresses, so
  `#delete[0x0AA]` deletes the hex-keyed variable, not "address 0x0AA".

---

## 5. `#delete` — the primary teardown

```cssc
#delete[name];
```

Frees the slot named `name` and runs a **destructor cascade** over its contents:
releasing a container walks its members and drops a reference on each; when a
referenced heap object reaches refcount 0 its own teardown runs (for objects, the
`free { }` block). You do **not** have to hand-track references — the cascade does
it. Your job is to write `#delete` where a slot must die before its default
end-of-life.

### 5.1 Cross-frame delete cascades the **whole reference chain**

When you delete a slot that is a **live reference** to a caller's slot (a function
parameter bound by `f(x)`, or a `#req` ref import), the delete propagates up the
**entire alias chain** — every source slot the reference transitively links to —
not just one level. R2 recurses `_ref_links` with an internal depth cap of **16**.

```cssc
#stack[int, 32] f;
#define(f) {
    #scanp(f, int, 0) p;   // p is a LIVE ref to the caller's argument slot
    #delete[p];            // frees p AND every source slot p links to
}

#stack[int, 32] x = 10;
f(x);                      // pass by reference (default)
cssc::outln(x);            // -> 0x0   (x released via the delete cascade)
```

Chained case — if `p` refers to `q` which refers to `y`, then `#delete[p]`
releases `p`, `q`, **and** `y`.

**But a copy is yours alone.** If the call site passes a copy (`h(&y)`), the param
is an independent slot, so `#delete[p]` frees only that copy — the original is
untouched:

```cssc
#stack[int, 32] h;
#define(h) {
    #scanp(h, int, 0) p;   // a param — but bound to a COPY at the call site below
    #delete[p];
}

#stack[int, 32] y = 10;
h(&y);                     // pass a COPY (call-site &)
cssc::outln(y);            // -> 10   (y survives; only the copy was freed)
```

**The rule in one line:** deleting a **reference** frees the referent (and its whole
chain); deleting a **copy** frees only the copy. Because CSSC binds by reference by
default (params, `#req`, `select` cursors), reach for `&` whenever you want an
independent lifetime — this is the same reason a `select` cursor must be copied to
outlive its loop (see [09 §5](09-control-flow.md)). Both branches above are verified
against `cssc run`: `f(x)` then `#delete[p]` prints `0x0`; `h(&y)` then `#delete[p]`
prints `10`.

Contrast this with **mutation write-back**: when you *assign to* a reference
parameter and the function returns, the new value is written back to the
**immediate caller's** slot only (one level). So the two cascades run in opposite
directions of depth:

- `#delete[ref]` -> **multi-level** (full chain, cap 16).
- ref-parameter mutation on return -> **one level** (immediate caller).

> **Impl-canonical note.** Some older notes state the opposite ("`#delete` is a
> single caller-level cascade; mutation cascades all levels"). That describes the
> **dead R1** runtime. The live **R2** runtime is as documented here: `#delete`
> recurses the full ref chain; mutation write-back is single-level. This was
> verified directly in `_delete_cross_frame` (R2) vs the R1 single-hop path.

### 5.2 The `0x0` guard for maybe-freed slots

`#adress[var]` as an expression yields the variable's address as an int, and
`0x0` when `var` is not bound. That is the idiomatic guard before a possibly
redundant delete (see §9).

---

## 6. `#delmember` — soft wipe (keep the container, drop the contents)

Use `#delmember` when you want to empty a container **without** freeing the
container's own allocation — e.g. a render buffer reused every frame.

| Form | Effect |
|---|---|
| `#delmember[container];` | Walk **all** entries, release each entry's heap content. `container.size()` and capacity are unchanged. |
| `#delmember[container[idx]];` | Wipe only entry `idx`. Its slot stays in the container (as null/0), other entries untouched. |

What "wipe" means per container:

| Container | `#delmember[c[i]]` | `#delmember[c]` |
|---|---|---|
| `vector<int\|float>` / `array<int\|float>` | `c[i] = 0` | all slots -> 0 |
| `map<string, int>` | bucket i: key released, value -> 0 | all buckets wiped |
| `bind<string, string>` | pair i: both strings released | all pairs wiped |
| `array<bind>` | entry i: heap content released, entry -> null | all entries wiped |

`#delmember` is **idempotent** (re-wiping a wiped slot is a no-op) and **safe on
null/empty** containers (no crash, just returns).

```cssc
#stack[array<bind>, 1024] Buffer;
tick:
    Buffer.push_back({0, 19, "hello"});
    render(Buffer);
    #delmember[Buffer];        // wipe content, keep the allocation
```

`#delete[c]` alone already releases members via the cascade, so
`#delmember[c]; #delete[c];` is redundant — just `#delete[c]`.

---

## 7. `#free` — objects, sectors, module aliases

`#free[X]` runs `X`'s `free { }` teardown block and then tears the entity down.
It is the correct teardown for **objects, sectors, and loaded module/`.obj`
aliases** — not `#delete`.

```cssc
#free[Engine];   // runs Engine's free { } then destroys the sector
#free[mh];       // releases a #depend'd .obj alias (mandatory; see 07-modules)
```

Summary of the three teardown operators:

| Operation | Container/entity | Contents |
|---|---|---|
| `#delete[c]` | freed | freed (cascade) |
| `#free[c]` | freed (object/sector/module) | freed (`free {}` block + cascade) |
| `#delmember[c]` | **kept** | freed |

---

## 8. Ownership & aliasing — what actually points at what

This is where the legacy docs are most misleading. The precise, impl-canonical
rules:

### 8.1 Plain assignment `b = a` is NOT a universal live reference

- **scalar (`int`, `float`, `bool`) -> value-copy.** `b` is an independent slot.
  Later mutation of `a` does **not** change `b`.
- **`string` -> value-copy.** Independent.
- **container (`array`, `vector`, `map`, `bind`, object, sector) -> alias.** `b`
  and `a` refer to the **same** underlying container; a mutation through either
  name is visible through the other.

```cssc
#stack[int, 32] a = 42;
#stack[int, 32] b = a;     // scalar -> VALUE COPY
a = 100;
cssc::outln(b);            // -> 42   (NOT 100)

#stack[vector<int>, 256] xs = [1, 2, 3];
#stack[vector<int>, 256] ys = xs;   // container -> ALIAS
xs.push_back(4);
cssc::outln(ys.size());    // -> 4   (same container)
```

> **Legacy docs are wrong here.** The old §8.1/§8.4 claim `#stack[int,32] alias =
> original;` makes `alias` a *live reference* so that mutating `original` later is
> visible through `alias`. That is **not** what the impl does for scalars/strings
> — those are value-copied on plain assignment. Only **containers** alias.
> Live cross-slot linkage for a scalar comes only from `#req` or argument passing
> (below), never from `b = a`.

### 8.2 Explicit deep copy: `&a`

`&a` is `cssc::copy(a)` — a **recursive deep copy**. It makes `b` fully
independent even for containers.

```cssc
#stack[vector<int>, 256] xs = [1, 2, 3];
#stack[vector<int>, 256] ys = &xs;   // deep copy
xs.push_back(4);
cssc::outln(ys.size());              // -> 3   (independent)
```

For scalars `&x` is indistinguishable from `x` (they are value types already).

### 8.3 Where live references actually come from

Only two mechanisms create a live cross-slot reference (a write through one is
seen through the other, for **all** types including scalars):

1. **`#req` import** — `#req[X] Y;` binds `Y` as a live ref to `X`
   (read/write-through). `#req[X] &Y;` is a deep-copy snapshot instead. See
   [03-scopes-and-req](03-scopes-and-req.md).
2. **Argument passing** — `f(x)` binds the callee parameter as a live ref to the
   caller's slot. `f(&x)` passes a deep copy. See [04-callables](04-callables.md).
   (The call *site* decides ref vs copy; a callee `&param` hint is **ignored**.)

### 8.4 Index references `list[i]`

Indexing a container yields a live view of the slot *inside* the container while
you operate on it in place (`list[i] = v` writes through). But binding it into a
**new scalar variable** follows the §8.1 rule — the scalar is value-copied:

```cssc
#stack[vector<int>, 256] list = [10, 20, 30];
list[1] = 99;                 // in-place write -> list is now [10, 99, 30]

#stack[int, 32] elem = list[1];   // scalar target -> VALUE COPY of 99
list[1] = 50;
cssc::outln(elem);                // -> 99   (unchanged; elem is not a live ref)
```

> **Legacy docs are wrong here too.** Old §8.4 claims `elem` stays live-linked to
> `list[1]`. It does not — the scalar is copied at assignment. To keep operating
> on the container slot, index it directly (`list[1]`), or import via `#req`.

### 8.5 Refcount cascade (containers holding your slots)

When you add a variable to a container, the container holds a reference to that
value. Deleting your local slot drops one reference, but the value survives as
long as the container holds it.

```cssc
#heap[array<auto>, 1024] queue;
{
    #stack[int, 32] a = 5;
    queue.add(a);      // queue references a's value
}                      // a's local slot is gone (bare {} barrier)
cssc::outln(queue[0]); // -> 5   (value lives on via queue)
#delete[queue];        // cascade releases queue[0]'s reference -> freed
```

---

## 9. `#adress` / `#reflect` — addresses and null-guarding

```cssc
#adress[var] addr;              // read the real memory address into addr
#reflect[addr] var;             // resolve an address back to its value

if (#adress[maybe] != 0x0) {    // guard: 0x0 means 'not bound'
    #delete[maybe];
}
```

- As a statement, `#adress[var] a;` stores the address.
- As an expression, `#adress[var]` is the address as an int, or `0x0` if unbound.
- `null` and `0x0` are the same null sentinel (see
  [01-types-and-values](01-types-and-values.md)).

> **Spelling matters.** The directive is `#adress` — **one `d`**. `#address`
> does **not** exist, and neither does `#memory` (the parser explicitly rejects
> `#memory` as a removed alias). Do not "correct" the spelling.

---

## 10. `#reallocate` / `#resize` / `#cast` / `#set`

```cssc
#reallocate[var, type, stack, 512] newvar;   // move var into a new region/size
#resize[buf, 64];                             // grow existing alloc by +64 bits
#resize[buf, -32];                            // shrink by 32 bits
```

- `#reallocate[var, type, stack|heap, size?] newvar;` — a **true region move**
  into a fresh `stack`/`heap` buffer. It is **type-strict** (no coercion — the
  `type` must match). If `size` is omitted it grows by the default `+32` bits.
- `#resize[var, ±bits];` — grow or shrink an existing allocation in place;
  follows the ref/pointer chain to the real buffer.
- `#cast[source, target] result;` — explicit coercion into an existing `#heap`
  target.
- `#set[0xADDR, bits] = value;` — write a coerced value at a known allocation
  address (bit-limit checked).

These are manual, RAW operations: no hidden copies beyond what you ask for, and
no automatic capacity growth for `#stack`/`#heap` (only `#auto` grows on its own).
Full syntax for every directive lives in [08-directives](08-directives.md).

---

## Common mistakes / impl-canonical notes

- **"Heap frees at end of block."** Only *barrier* blocks (§3). `if`/`for`/
  `while`/`select` do not free their inner heap allocations.
- **"`b = a` makes `b` track `a`."** Only for **containers** (alias). Scalars and
  strings are value-copied (§8.1). Legacy §8.1/§8.4 say otherwise and are wrong.
- **"`#delete` on a ref only frees my local copy."** No — it cascades up the
  **entire** reference chain and frees every source slot the ref links to
  (§5.1). If you meant to keep the caller's slot, pass `f(&x)` (copy) or don't
  delete.
- **Delete vs mutation cascade depth are opposite.** `#delete` = multi-level
  (full chain, cap 16); ref-parameter mutation write-back on return = one level
  (immediate caller). Older notes state this backwards — that is the dead R1
  runtime (§5.1).
- **"Stack/auto get cleaned up for me."** Never. `#stack` and `#auto` leak unless
  you `#delete`. Only `#heap` self-cleans (at program end).
- **`#delmember` vs `#delete`.** `#delmember` keeps the container and wipes
  contents; `#delete` frees the container too.
- **Objects/sectors/modules use `#free`, not `#delete`** — `#free` runs their
  `free { }` block.

## See also

- [03-scopes-and-req](03-scopes-and-req.md) — isolation barriers, `#req` ref vs snapshot.
- [04-callables](04-callables.md) — call-site ref/copy, `mirror` vs `return`.
- [01-types-and-values](01-types-and-values.md) — what "scalar" vs "container" means, `null`/`0x0`.
- [08-directives](08-directives.md) — canonical syntax for every `#…` directive.
