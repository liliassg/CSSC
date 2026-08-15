# 09 — Control Flow

`if` / `for` / `while` are conventional. `select` is not — it is a **cursor**
loop driven by explicit `jump` statements, and it is the one construct people
misuse. This chapter covers all of it.

> **Scope reminder.** `if`, `else`, `for`, `while`, and `select` bodies are
> **not** isolation barriers — they see the enclosing scope directly, so you do
> **not** need `#req` inside them. (Only `#define`/`{}`/object/label/sector bodies
> are barriers — see [03-scopes-and-req](03-scopes-and-req.md).)

---

## 1. `if` / `else if` / `else`

```cssc
if (x > 10) {
    cssc::outln("big");
} else if (x > 5) {
    cssc::outln("medium");
} else {
    cssc::outln("small");
}
```

The condition is truthy/falsy in the usual way; recall `0`, `0x0`, and `null` all
compare equal (see [01-types-and-values §4](01-types-and-values.md)).

---

## 2. `for`

Three forms:

```cssc
// C-style
for (int i = 0; i < 10; i = i + 1) {
    cssc::outln(i);
}

// for-in over values
for (val in myList) {
    cssc::outln(val);
}

// for-in with index
for (i, val in myList) {
    cssc::outln(i + ": " + val);
}
```

The loop variable (`i` / `val`) is local to the loop and released at the closing
`}`. The body still sees the enclosing scope (it is not a barrier).

---

## 3. `while`

```cssc
while (running) {
    cssc::outln("tick");
}
```

---

## 4. `break` / `continue`

- `break;` — exit the nearest `for` / `while` loop.
- `continue;` — skip to the next iteration of the nearest `for` / `while` loop.

Note the special case in object labels: a `break;` in a **label body but outside
any loop** acts as an early return from the label (see
[05-objects §6](05-objects.md)).

---

## 5. `select` — cursor iteration (needs a `jump`)

`select` walks an iterable with an explicit **cursor**. Each pass binds the
current element to `?name`; you then decide how far to move the cursor with a
`jump`. **If you never `jump`, the cursor never advances** — the body runs at most
once and the loop ends. That is almost always a bug, and the LSP flags it
(`SELECT_WITHOUT_JUMP`).

```cssc
#stack[array<int>, 1024] bytecode = {9, 8, 7, 6, 5, 4, 3, 2, 1, 0x0};

select (bytecode) ?i {
    if (i == 0x0) {          // sentinel -> stop
        cssc::outln("end");
        return;              // 'return' exits the WHOLE function, not just select
    }
    if (i == 1) {
        jump++;              // skip the next element (cursor +2)
    }
    cssc::outln(i);
    jump;                    // advance to the next element (cursor +1)
}
```

### Cursor controls

| Statement | Cursor move |
|---|---|
| `jump;` | +1 (next element) |
| `jump++;` | +2 (skip one) |
| `!jump;` | -1 (back one) |
| `!jump++;` | -2 (back two) |

- **No `jump` on a path** = the cursor does not move on that path; when control
  reaches the end of the body with no jump, the loop **terminates**.
- **Cursor out of bounds** = loop ends.
- `return;` inside a `select` exits the **enclosing function/label**, not merely
  the loop. To leave just the loop, arrange your `jump`s so the cursor runs out
  (or use a sentinel like `0x0`).

> **Impl-canonical note.** The backward form is `!jump` / `!jump++` — there is no
> `jump_back` keyword. `jump` is the only cursor keyword; the leading `!` negates
> the direction and `++` doubles the step.

### `?i` is a **reference** — copy it (`&i`) to keep it beyond the loop

The cursor `?i` is a **borrowed reference into the iterated container** — CSSC binds
by reference by default (params, `#req`, and cursors alike; see
[02 §8](02-memory-and-ownership.md) and [04 §3](04-callables.md)). It is valid only
**during the current pass**: the next `jump` rebinds it to the next element, and when
the `select` exits it goes dead. Storing the *bare* cursor anywhere that outlives the
loop leaves a stale reference that reads `0x0`:

```cssc
#heap[vector<int>, 1024] kept = [];
select (nums) ?i {
    kept.push(i);      // WRONG — stores a BORROWED reference; dead after the loop
    jump;
}
// kept[0] now reads 0x0 — the cursor it pointed at is gone
```

Hand over a **copy** with `&` so the value outlives the cursor:

```cssc
select (nums) ?i {
    kept.push(&i);     // RIGHT — &i is an independent copy that survives the loop
    jump;
}
```

This is the same rule as delete-a-reference-vs-a-copy
([02 §5](02-memory-and-ownership.md)): **by default you hold the real thing, not a
copy** — so anything you want to keep past the cursor's lifetime must be copied with
`&`. The LSP flags the bare-reference case as `SELECT_ALIAS_BORROW_NO_COPY`, and
`#delete[?i]` / `#free[?i]` (freeing the borrowed cursor) as `DELETE_SELECT_ALIAS`.

### `?label.pos()` — current cursor index

Inside the body, `?label.pos()` gives the current 0-based cursor position.

```cssc
#stack[list, 256] n = [10, 20, 30];
select (n) ?i {
    cssc::out("pos=");
    cssc::out(i.pos());     // 0, 1, 2
    cssc::out(" val=");
    cssc::outln(i);
    jump;
}
```

> **Backend note.** The native compiler currently lowers `select` only for
> `vector<int>` and `array<bind>`. For embedded builds, prefer those container
> kinds; other iterables (`array<float>`, `map`, `bind`) are interpreter-only for
> now. Semantics are identical across backends where supported.

---

## Common mistakes / impl-canonical notes

- **`select` with no `jump` runs once and stops.** Every path that should
  continue iterating must end in a `jump` (or `jump++`, `!jump`, …). The LSP lint
  `SELECT_WITHOUT_JUMP` catches the missing-jump case.
- **`return;` in a `select` exits the function**, not just the loop. Use a
  sentinel or let the cursor run out to end only the loop.
- **`if`/`for`/`while`/`select` are not barriers.** They read and write the
  enclosing scope; do not wrap outer names in `#req` inside them.
- **Backward jump is `!jump`,** not `jump_back`.

## See also

- [03-scopes-and-req](03-scopes-and-req.md) — why these blocks are transparent (non-barriers).
- [01-types-and-values](01-types-and-values.md) — `0x0`/`null` truthiness used in conditions.
- [05-objects](05-objects.md) — `break` as label early-return.
