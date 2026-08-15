# 05 — Objects

An `object` bundles **data members** (accessed with `->`) and **labels**
(named code sections, called with `.`). Objects are instantiated, can be cloned,
support label overloading, and run a mandatory `free { }` teardown block.

The two access operators used with objects are **not** interchangeable — see
[10-access-operators](10-access-operators.md) for the full rules. In short:
`obj->member` reads/writes a **data member**; `inst.label(args)` **calls a label**.

---

## 1. Structure

```cssc
object Player {
    #auto[int] Player->hp = 100;    // data member, declared with ->
    Player->init();                 // top-level object code runs at instantiation

init:                               // a label (named code section)
    cssc::outln("Player created");

takeDamage<int: dmg>:               // a label with a typed parameter
    Player->hp = Player->hp - dmg;
    if (Player->hp <= 0) {
        call die;
    }

die:
    cssc::outln("Player died");
    destruct;                       // run free {}, mark dead, return to caller
} free {
    #delete[Player->hp];            // mandatory teardown
};
```

- **Data members** are declared and accessed as `Player->member`.
- **Labels** are `name:` sections; the object's top-level statements (outside any
  label) run once at instantiation.
- **`free { }` is mandatory** and runs on `#free[instance]` (or on `destruct`).
- The object body is an **isolation barrier** (see
  [03-scopes-and-req](03-scopes-and-req.md)); members are the object's own scope.

---

## 2. Instantiation and calling labels

```cssc
Player() myPlayer;          // run the object's top-level code, bind the instance
myPlayer.takeDamage(30);    // call a label with '.'
```

- `Type() name;` instantiates. Constructor arguments go in the parentheses (§4).
- `instance.label(args)` calls a label. Labels are the object's callable surface.

---

## 3. Data members: `->` (no access check)

Member access uses `->`, and — this is the important asymmetry — **`->` performs
no access-control check**. A member reached with `->` is always reachable, even
from outside the object, even if you intended it to be "private".

```cssc
Player() p;
cssc::outln(p->hp);     // works from outside — -> is not gated
```

> **Impl-canonical note (asymmetry).** **Objects have no access control at all** —
> every member (`->`) and label (`.`) is always reachable. Access control is a
> **sector** feature: sector members reached with `::` are gated by
> `public:`/`private:` (a private read → `0x0`). So `::` (on a sector) enforces
> privacy; `->` never does. This is a deliberate asymmetry, not a doc bug — see
> [10-access-operators](10-access-operators.md) and §7 below.

---

## 4. Constructor parameters and `<…>` injection (capture)

The `<…>` header on an object is its **capture/injection list**. Each entry is
one of:

| Form | Meaning |
|---|---|
| `<type: name>` | **Constructor parameter** — supplied at instantiation, typed. |
| `<name>` | **Zero-copy reference** captured from the enclosing scope (v6 default). |
| `<&name>` | **Deep copy** captured from the enclosing scope. |
| `<*name>` | **Deprecated** ref spelling; identical to bare `<name>`. |

Constructor parameters:

```cssc
object Widget<int: width, int: height> {
    #stack[int, 32] Widget->w = width;
    #stack[int, 32] Widget->h = height;
} free {
    #delete[Widget->w];
    #delete[Widget->h];
};

Widget(800, 600) myWidget;
```

Scope capture (composition / inheritance-like): injecting an outer object or
sector into an object's header captures it as a live (or copied) member, which is
how CSSC expresses composition without a class-inheritance keyword:

```cssc
#stack[int, 32] globalConfig = 42;

object App<globalConfig> {          // captured by reference (v6 default)
    // globalConfig is available here as a zero-copy reference
} free {};

object Snapshot<&array<int>: buf> { // captured as an independent deep copy
    // mutating the original after construction is not visible here
} free {};
```

> **Legacy note.** The old `object Foo<*a, *b>` ref spelling is deprecated but
> still accepted; write `object Foo<a, b>` (ref) or `object Foo<auto: a, auto: b>`
> for constructor params. Bare capture is ref-by-default, matching `#req` and
> argument passing.

---

## 5. Labels: parameters, transfers, overloading

```cssc
object Handler {
    process<string: data>:
        cssc::outln("String: " + data);
    process<int: data>:                 // same name, different parameter type
        cssc::outln("Int: " + data);
} free {};

Handler() h;
h.process("hello");   // -> "String: hello"
h.process(42);        // -> "Int: 42"
```

- **Simple label:** `name:`
- **Typed parameters:** `name<int: x, string: msg>:`
- **Transfer capture:** `name<outerVar>:` — captures an outer variable
  zero-copy into the label (v6 default; `<*outerVar>` is the deprecated spelling).
- **Overloading:** several labels may share a name with different parameter
  lists. Resolution is at **runtime by argument types**; an exact type match wins.

---

## 6. `call`, `mirror`, `return`, `destruct`

Inside an object, labels invoke each other with `call`, and hand back values with
`mirror` / `return` (identical semantics to [04-callables §8](04-callables.md)).

```cssc
object Calculator {
    add<int: a, int: b>:
        mirror a + b;       // return the value, keep running for cleanup

    snapshot<data>:
        mirror &data;       // explicit deep-copy return

    shutdown:
        destruct;           // run free {}, mark dead; host keeps running
} free {};

Calculator() calc;
call add<3, 4> result;      // call a label with transfer args, capture -> 7
```

- `call label<args> capture;` — call a label and bind its result.
- `call label<*name, 42>;` — the `*name` transfer form forces an explicit transfer
  reference instead of the automatic scope pull (`*` here is a transfer override,
  not the deprecated ref marker).
- `destruct;` — runs `free { }`, marks the instance dead, and **returns to the
  caller** (it is not `exit()`; the host script continues).
- `break;` inside a label (outside any loop) acts as an **early return** from the
  label — it does not destroy the object. Inside a `for`/`while` it is the normal
  loop break.

See [04-callables §8](04-callables.md) for the full `mirror` live-ref vs snapshot
rules.

---

## 7. Objects have no access control — use a sector for privacy

**Objects do not have `public`/`private`.** Access control is a **sector** feature,
not an object one (this is by design). Every object member (via `->`) and every
label (via `.`) is always reachable from anywhere; there is no object-level privacy
and no modifier that turns it on.

If you need enforced privacy, put the state in a **sector** — `::` access honours
`public:` / `private:`, and a private read returns `0x0`:

```cssc
sector Config {
private:
    secret = "internal only";
public:
    show:
        cssc::outln(Config::secret);   // internal read — allowed
} free {};

cssc::outln(Config::secret);   // external read of a PRIVATE member -> 0x0
```

> **Impl-canonical note.** Legacy docs show a `secure !` object modifier and object
> `private:`/`public:` sections (with external private access returning `0x0`).
> That is **not** an object feature — objects carry no access control, so any such
> markers on an object are inert. Privacy lives in sectors. See
> [06-sectors](06-sectors.md).

---

## Common mistakes / impl-canonical notes

- **Objects have no privacy.** Every object member (`->`) and label (`.`) is always
  reachable. Access control is a **sector**-only feature; `::` on a sector enforces
  `public:`/`private:`. There is no object-level privacy modifier.
- **`.` vs `->`.** `.` calls a **label**; `->` reads/writes a **data member**.
  They are not interchangeable — see [10-access-operators](10-access-operators.md).
- **`free { }` is mandatory** and must release every member you allocated.
- **`destruct` is not exit.** It tears down the instance and returns to the host.
- **Overloading is runtime, by argument type.** Exact type match wins.
- **Captures are ref-by-default.** `<name>` is a live ref; `<&name>` deep-copies;
  `<*name>` is deprecated.

## See also

- [10-access-operators](10-access-operators.md) — the definitive `::` vs `->` vs `.` rules.
- [06-sectors](06-sectors.md) — sectors enforce `::` privacy (the counterpart asymmetry).
- [04-callables](04-callables.md) — `mirror`/`return`/`destruct`, capture syntax.
- [02-memory-and-ownership](02-memory-and-ownership.md) — `#free` teardown, member cascade.
