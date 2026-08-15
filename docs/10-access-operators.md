# 10 — Access Operators: `::` vs `->` vs `.`

This is the **#1 source of CSSC mistakes**. The three access operators are **not
interchangeable**, and legacy language docs get this wrong. The rules below are
what the canonical R2 runtime actually does.

> If you remember one thing: **`::` = namespace (sectors/modules, privacy
> enforced) · `->` = data member (objects/sectors, privacy NOT enforced) · `.` =
> object label/method call.**

---

## 1. Decision table

| Operator | Use it for | Access-controlled? | Private member | Missing member |
|---|---|---|---|---|
| `::` | **sector / module** namespace member — `alias::member`, `alias::func(args)` | **Yes**, on reads | read -> `0x0` (null); a `::` **write** bypasses the check and **persists** | sector -> `null`; **builtin-module method call -> ERROR**; module property read -> `null` |
| `->` | **object / sector data member** — `obj->field`, `Sector->field` | **No** | fully **readable and writable** | read -> `null` |
| `.` | **object label / method call** — `instance.label(args)` | No (enforcement is inert in R2) | reachable / callable | method call -> **ERROR** "No method"; property read (no parens) -> `null` |

---

## 2. `::` — namespace access (sectors and modules)

Use `::` to reach a **public** member of a sector, or a member of a loaded
module.

```cssc
App::run();                 // call a public sector function
cssc::outln(App::title);    // read a public sector member
mh::mathlib::square(7);     // reach into a #depend'd .obj (nested namespaces)
```

`::` **enforces public/private on reads**: reading a `private:` sector member
through `::` returns `0x0` (null), *not* an error.

> **Asymmetry to internalise.** A `::` **write** to a sector member is **not**
> access-checked and **does persist** in the interpreter (`App::secret = 5;`
> actually stores). Only the *read* side of `::` is gated. (Legacy
> `cssc-sectors.md` says an external `::` write is a silent no-op; R2 persists it —
> impl wins.)

Missing-member behavior differs by target (this is the module-vs-sector
asymmetry — see [07-modules](07-modules.md)):

- **sector**, missing/private member -> `null`;
- **builtin module**, missing *method* call `mod::nope(...)` -> **runtime error**
  `"Module 'mod' has no function 'nope'"`;
- **module**, missing *property* read `mod::nope` -> `null`.

---

## 3. `->` — data member access (objects and sectors), NOT access-checked

Use `->` to read or write a **data member** of an object or a sector.

```cssc
object Player {
    #auto[int] Player->hp = 100;    // declare a member with ->
} free {};

Player() p;
cssc::outln(p->hp);     // read a member
p->hp = 50;             // write a member
```

**`->` performs no access-control check.** This is the deliberate asymmetry with
`::`: a sector's `private:` member is hidden from a `::` read but is fully
reachable — and writable — through `->`.

```cssc
sector Vault {
private:
    #stack[int, 32] Vault->secret = 42;
public:
    #stack[int, 32] Vault->label = 1;
} free {};

cssc::outln(Vault::secret);   // -> 0x0    (:: read is gated -> null)
cssc::outln(Vault->secret);   // -> 42     (-> is NOT gated -> real value!)
Vault->secret = 0;            // -> allowed (-> write is not gated either)
```

> **Impl-canonical note.** This `::`-gated / `->`-ungated split is real and
> intentional in R2. Do not assume `private:` protects a member from `->`. If you
> need enforced privacy, keep secrets reachable only through `::` and never expose
> a `->` path to them.

---

## 4. `.` — object label / method call

Use `.` to **call a label** (method) on an object instance.

```cssc
Handler() h;
h.process("hello");     // call the 'process' label
h.process(42);          // overload resolved at runtime by argument type
```

- `.` with parentheses is a **method/label call**. Calling a label that does not
  exist raises a runtime error (`"No method '…'"`).
- `.` without parentheses is a property read; a missing one yields `null`.
- Object-level access control (`private:` labels, `secure !`) is **inert** in R2 —
  every label is callable regardless (see [05-objects §7](05-objects.md)).

---

## 5. Wrong vs right

| Wrong | Right | Why |
|---|---|---|
| `p.hp` to read a member | `p->hp` | `.` is for label calls; data members use `->`. |
| `p->takeDamage(30)` to call a label | `p.takeDamage(30)` | Labels/methods are called with `.`, not `->`. |
| `obj::field` on an object | `obj->field` | `::` is for sector/module namespaces, not object instances. |
| relying on `Vault->secret` being blocked | read secrets via `Vault::secret` only | `->` is never access-checked; `::` read is. |
| `Sector.func()` | `Sector::func()` | Sector/module calls use `::`. |
| expecting `Vault::secret` to error | it returns `0x0` | Private `::` read is a null, not an error. |

---

## 6. Quick mental model

```
alias::member      ->  sector/module namespace   (public/private ENFORCED on read)
entity->member     ->  object/sector data field  (NO access check, read + write)
instance.label()   ->  object label / method     (call; overload by arg type)
```

---

## Common mistakes / impl-canonical notes

- **They are not interchangeable.** `::`, `->`, `.` each have one job. Legacy docs
  that treat them as loosely swappable are wrong — the impl is strict.
- **`->` ignores privacy.** A private sector member is readable *and* writable via
  `->`. Only `::` reads are gated.
- **`::` write persists** on sectors (not a no-op).
- **Missing member is inconsistent by target:** null for sectors/properties, but a
  hard error for a missing builtin-module method call and a missing object method
  call.
- **Object privacy (`.`/`secure !`) is not enforced in R2.** Use a sector for real
  privacy.

## See also

- [06-sectors](06-sectors.md) — `::` public/private enforcement, isolation.
- [05-objects](05-objects.md) — `->` members, `.` labels, `secure !` (inert).
- [07-modules](07-modules.md) — module `::` dispatch and the missing-member asymmetry.
