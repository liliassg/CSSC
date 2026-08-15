# 04 — Callables (`#define`, params, `mirror`/`return`)

CSSC has an unusual but consistent model: **a function is a variable**. There is
no separate "function" entity. You declare a slot, then bind a *worker* (a body)
to it. Calling the slot runs the worker.

---

## 1. Variables are callables (the duality)

```cssc
#stack[int, 32] add;      // 1. declare a slot
#define(add) {            // 2. bind a worker to that slot
    #req[a] a;
    #req[b] b;
    return a + b;
}
```

Internally the slot gains two facets:

- `add["value"]` — the **last return value** (or `null` if never called),
- `add["address"]` — the address of the worker.

Calling `add(…)` runs the worker and stores its result in `add["value"]`. This
duality is why you can `#req` a function by name and call it (see
[03-scopes-and-req §5](03-scopes-and-req.md)), and why the same slot can hold both
a value and behaviour.

The **`#define` body is an isolation barrier** — it does not see outer names.
Import them with `#req` (see [03-scopes-and-req](03-scopes-and-req.md)).

---

## 2. `#define` — the core form

```cssc
#stack[int, 32] greet;
#define(greet) {
    #req[name] who;                 // import an outer slot by ref
    #stack[string, 64] m = "Hi " + who;
    cssc::outln(m);
    #delete[m];
}
```

- `#define(slot) { body }` binds `body` to `slot`.
- `#define` is **core** — it needs no module.
- The body runs in a private, isolated scope (barrier).
- `return` exits the body with a value (see §8).

---

## 3. `#cdefine` — named-parameter form (needs the `def` module)

`#cdefine` lets you name parameters in the signature instead of scanning them by
position.

```cssc
#include('def');

#stack[int, 64] multiply;
#cdefine(multiply, a, b) {
    return a * b;
}
cssc::outln(multiply(3, 4));   // -> 12
```

> **Module gate.** `#cdefine`, `#fvar`, `#param`, `#qvar` are gated behind the
> **`def`** module — put `#include('def');` once at the top or you get a clear
> "missing module" error. `#define` and `#redefine` are core.
>
> **Impl-canonical note.** `#scanp` and `#scanp_opt` are documented as part of the
> `def` family, but R2 does **not** actually enforce a module gate on either
> (both parse to the same node and the gate check is never reached). They work
> without `#include('def')` in the interpreter. Keep the `#include('def');`
> anyway if you use the rest of the family, for portability to the native path.

---

## 4. Reading parameters: `#scanp` / `#scanp_opt`

```cssc
#include('def');

#stack[int, 32] sum;
#define(sum) {
    #scanp(sum, int, 0) x;             // mandatory arg at position 0
    #scanp(sum, int, 1) y;             // mandatory arg at position 1
    #scanp_opt(sum, int, 2) bonus = 0; // optional; missing -> default 0
    return x + y + bonus;
}

sum(10, 20)    a;   // -> 30
sum(10, 20, 5) b;   // -> 35
```

- `#scanp(source, type, pos) name;` — read the **mandatory** call argument at
  `pos`. `source` is the callable's own name.
- `#scanp_opt(source, type, pos) name;` — **optional**: if no argument and no
  default is present, `name` resolves to `null` instead of erroring.
- Both accept a default clause: `#scanp_opt(sum, int, 2) bonus = 100;` uses `100`
  when the argument is absent.
- `#scanp_opt` yields `null` **only** when neither an argument nor a default was
  supplied — ideal for variadic-style trailing arguments.

### The parameter's ref/copy nature is decided by the CALL SITE (see §7)

`#scanp(f, int, 0) name;` — `name` is a **live reference** to the caller's slot
when the caller passed `f(x)`, or an **independent copy** when the caller passed
`f(&x)`. A `&` or `*` on the parameter name is **not** what decides it:

- `#scanp(f, int, 0) &name;` — a **hint** that the callee prefers a copy. The
  runtime **ignores** the `&`; only the call site decides.
- `#scanp(f, int, 0) *name;` — **deprecated** legacy ref spelling; identical to
  bare `name`.

---

## 5. `#fvar`, `#param`, `#qvar` (needs the `def` module)

```cssc
#fvar(int) counter;          // typed function variable (declares a return-typed slot)
#param(string) inputStr;     // typed parameter for the next #cdefine
#qvar(int, x + y) result;    // quick variable from an expression
```

- `#fvar(type) name;` — declare a typed callable-variable up front.
- `#param(type) name;` — declare a typed parameter (written only via `#scanp`).
- `#qvar(type, expr) name;` — materialise `expr` into a typed local in one line.

---

## 6. Calling and capturing results

A call can be a bare statement, an expression, or a **capture** that binds the
return value to a new slot:

```cssc
add(3, 4);            // call, discard result (still stored in add["value"])
#stack[int, 32] r = add(3, 4);   // capture via assignment
add(3, 4) r2;         // capture form: bind result into a new slot r2
```

The `f(args) name;` capture form is the idiomatic way to name a call's result.

---

## 7. Call-site ref vs copy — `f(x)` vs `f(&x)`

This is the rule that mirrors the ownership chapter. **The call site decides**
whether an argument is passed by reference or by copy. The callee cannot override
it.

```cssc
#stack[int, 32] f;
#define(f) {
    #scanp(f, int, 0) p;   // ref or copy depends on how f was CALLED
    #delete[p];            // deletes p; if p was a ref, deletes caller's slot too
}

#stack[int, 32] x = 10;
f(x);                      // pass by REFERENCE (default)
cssc::outln(x);            // -> 0x0   (p was a live link; #delete[p] took x too)

#stack[int, 32] y = 10;
f(&y);                     // pass a COPY (explicit &)
cssc::outln(y);            // -> 10    (p was independent; only the copy died)
```

- `f(x)` — **reference** (default). Mutations and a `#delete` inside `f` reach the
  caller's slot (one level up — see
  [02-memory-and-ownership §5.1](02-memory-and-ownership.md)).
- `f(&x)` — **deep copy**. The callee gets an independent slot.
- `f(*x)` — **deprecated** legacy spelling of the ref form; identical to `f(x)`.

> **Impl-canonical note.** A callee-side `&param` hint (`#scanp(f,int,0) &p;`) is
> **ignored** by the runtime. Only the call-site syntax matters. Legacy docs that
> present `&param` as "the callee forces a copy" are wrong — it is documentation
> intent only.

---

## 8. `mirror` vs `return` vs `destruct`

All three end (or pause) a body, but they differ in **what happens after**.

| Form | After it runs | Return value binding |
|---|---|---|
| `return value;` | **Hard short-circuit.** Body stops immediately; trailing cleanup does **not** run. | value |
| `mirror value;` | **Body keeps running** — trailing `#delete` / `#free` still execute. Default: a **live ref** to the source slot. | value (live ref) |
| `mirror &value;` | Like `mirror`, but a **deep-copy snapshot** taken at the `mirror` point. Later cleanup can't disturb it. | value (snapshot) |
| `mirror *value;` | **Deprecated** alias of `mirror value;`. | value (live ref) |
| `destruct;` | Object only: runs the object's `free { }` block, marks it dead, control returns to the caller. Not `exit()`. | — |

### Why `mirror` exists

`return` cannot both hand back a value **and** clean up afterwards. `mirror` can:
it sets the return value but lets the rest of the body run, so you can free copy
parameters and transient allocations before the call actually returns.

The subtlety is the **live-ref default**: if you `mirror` a *slot* and then delete
that slot, the outer capture is invalidated:

```cssc
#stack[int, 32] f;
#define(f) {
    #stack[int, 32] inner = 42;
    mirror inner;          // live ref to inner
    #delete[inner];        // inner freed -> the outer capture is now 0x0
}
f() out;
cssc::outln(out);          // -> 0   (NOT 42 — the ref was invalidated)
```

Snapshot fixes it:

```cssc
#define(f) {
    #stack[int, 32] inner = 42;
    mirror &inner;         // snapshot copy
    #delete[inner];        // inner freed, but the snapshot survives
}
f() out;
cssc::outln(out);          // -> 42
```

And **mirroring an expression** (not a slot) is automatically a snapshot, because
there is no slot to be a reference to:

```cssc
#define(f) {
    #scanp(f, int, 0) n;
    #scanp(f, int, 1) t;
    mirror n + t;          // expression -> automatic snapshot
    #delete[t];
    #delete[n];
}
f(&a, &b) r;               // r holds the value safely
```

**Rule of thumb:** if the body cleans up the very thing it returns, use
`mirror &x;`. If cleanup touches a *different* slot, plain `mirror x;` is fine.
If there is nothing to clean up, `return x;` is simplest.

`destruct` and object-label mechanics are covered in
[05-objects](05-objects.md).

---

## 9. `#redefine` — mutate a function body (interpreter-only)

```cssc
#redefine(myFunc) { cssc::outln("overwritten"); }   // replace whole body
#redefine(myFunc) +<0> { cssc::outln("prepended"); } // inject at position 0
```

- Without a position: replaces the entire body.
- With `+<pos>`: injects code at statement position `pos`.

> **Backend note.** `#redefine` is **interpreter-only** (`cssc run`). The native
> compiler lowers function bodies statically, so a runtime AST mutation has no
> effect there. For native builds, use `if`/`select` branching or parameterise
> with `#cdefine`.

---

## Common mistakes / impl-canonical notes

- **A callee `&param` hint does nothing.** Ref vs copy is a call-site decision
  (`f(x)` vs `f(&x)`). The `&` on `#scanp … &name;` is ignored by the runtime.
- **`return` skips cleanup.** If you have copy-params or transient allocations to
  free, use `mirror` so the trailing `#delete`s still run.
- **`mirror slot;` is a live ref.** Deleting that slot afterwards zeroes the
  caller's capture. Use `mirror &slot;` to snapshot.
- **`#cdefine`/`#fvar`/`#param`/`#qvar`/`#scanp_opt` need `#include('def')`.**
  `#define`/`#redefine`/`#scanp` are core.
- **`#define` bodies can't see outer names.** Import via `#req`.

## See also

- [03-scopes-and-req](03-scopes-and-req.md) — `#define` body is a barrier; `#req` imports.
- [02-memory-and-ownership](02-memory-and-ownership.md) — call-site ref/copy, delete cascade.
- [05-objects](05-objects.md) — labels, `call`, `destruct`, label overloading.
- [08-directives](08-directives.md) — canonical syntax for all `#…` forms.
