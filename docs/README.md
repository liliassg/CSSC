# CSSC Language Documentation
### Control Specified Source Compiling — Complete Reference
**Version 6.0** | Mai 2026

---

## 1. Was ist CSSC?

CSSC (Control Specified Source Compiling) ist eine kompakte, hardwarenahe Skriptsprache mit manueller Speicherverwaltung, strikter Typisierung und einem einzigartigen Architekturmodell. Im Kern ist CSSC ein System, in dem **alles eine Variable ist** — Funktionen, Sektoren, Objekte, Module. Jede Variable existiert auf dem Stack oder Heap als ein Puffer fester Groesse (in Bits), der vom Programmierer explizit allokiert und freigegeben werden muss.

**Zielplattform: embedded systems.** CSSC ist primär für Mikrocontroller und ressourcen-beschränkte Geräte entworfen — daher die obsessiv **bit-genaue** Allokation (`#stack[int, 32]`, `#stack[string, 256]`), das fehlende Garbage-Collection-System und die explizite Free-Pflicht. Auf einem ESP32 mit 320 KB SRAM willst du WISSEN, wo deine 32 Bit hingehen. Für Skripte auf Desktop-Hosts wo Bit-Buchhaltung overhead wäre, gibt's `#auto` als bewussten Escape-Hatch (siehe 2.3).

Native-Builds für **ESP8266, ESP32, Arduino und Raspberry Pi** werden direkt von `cssc build --esp8266` / `--esp32` / `--arduino` / `--raspberry` unterstützt; siehe Section 10.5b. Plus die Embedded-Toolchain: `cssc flash` (esptool/avrdude), `cssc scan` (Port-/I²C-Discovery), `cssc install --library` (Arduino-Bibliotheken → CSSC `.obj`-Bundle) — Sections 10.5c–10.5e.

### Grundprinzipien

- **Alles ist eine Variable**: Eine Funktion ist nichts anderes als eine Variable, der eine Worker-Adresse zugewiesen wurde. `#define(myFunc)` erstellt intern `myFunc["value"]` (letzter Rueckgabewert) und `myFunc["address"]` (Adresse des Workers).
- **Explizite Speicherverwaltung**: Der Programmierer entscheidet, wo und wie gross Daten gespeichert werden (`#stack`, `#heap`, `#auto`). Jede Allokation bekommt einen ctypes-Puffer mit fester Bit-Kapazitaet.
- **Strenge Host-Verantwortung**: Wer etwas erzeugt, muss es auch aufraeumen. Jeder `#stack` braucht ein `#delete`, jeder `sector` ein `#free`, jedes `#include` ein `#free`.
- **Keine versteckten Abstraktionen**: Es gibt keine Garbage Collection, kein automatisches Scope-Cleanup (ausser `#heap`), keine impliziten Kopien.
- **Bit-Präzision aus Embedded-Mindset**: Allokationen geben Bit-Kapazität an, nicht Byte oder Element-Anzahl. Ein `#stack[int, 32] x = 5;` reserviert exakt 32 Bits — ein Überlauf (z.B. `x = 0xFFFFFFFFFF`) ist ein expliziter Runtime-Fehler, kein silent UB. `#auto` lockert das nur dort wo's pragmatisch ist.

---

## 2. Speicherallokation

### 2.1 Stack (`#stack`)

```cssc
#stack[string, 256] name = "Hello";
```

- Allokiert einen ctypes-Puffer mit **256 Bits** Kapazitaet
- Der Wert wird in UTF-8 kodiert und in den Puffer geschrieben
- **Manuelles `#delete[name]` ist Pflicht** — sonst Memory Leak
- Der Puffer hat eine feste Groesse: Ueberlauf (`value > capacity`) ist ein Laufzeitfehler

#### Hex-Identifier statt Variablenname

Ein hex-Literal kann anstelle eines Variablennamens stehen. Die Variable lebt
dann im globalen Hex-Storage statt im benannten Scope — Lookup ueber
`uint64`-Key statt String-Vergleich.

```cssc
#stack[int, 32] 0x0AA = 42;
cssc::outln(0x0AA);     // 42 — wird als Var-Lookup interpretiert
#delete[0x0AA];
```

- Praktisch fuer Embedded/Performance-kritischen Code, wo String-Lookups
  unerwuenscht sind
- Das gleiche Hex-Literal in einem **arithmetischen** Ausdruck bleibt einfach
  Integer-Konstante, wenn keine Variable mit diesem Key existiert
- Kollidiert nicht mit `#delete[0xADDR]`-Memory-Adressen (hex-keyed Vars
  werden zuerst geprueft)

### 2.2 Heap (`#heap`)

```cssc
#heap[vector<int>, 1024] data = [1, 2, 3];
```

- Allokiert auf dem Heap
- **Automatisch freigegeben** am Ende der Ausfuehrung
- Kein manuelles `#delete` noetig (aber empfohlen fuer fruehes Freigeben)
- Groessere Kapazitaeten moeglich

### 2.3 Auto (`#auto`)

```cssc
#auto[int] counter = 0;
```

- Auto-sizing: Der Puffer waechst automatisch bei Bedarf
- **Manuelles `#delete[counter]` ist Pflicht**
- Kein `bits`-Parameter noetig — die Groesse passt sich an

### 2.4 Wie Speicher intern funktioniert

Jede Allokation erzeugt einen Eintrag in `_stack_vars`, `_heap_vars` oder `_auto_vars`:

```
{
  "type": "string",
  "max_bits": 256,
  "buffer": <ctypes.c_char_Array>,
  "region": "stack"
}
```

Der Wert wird mit `_encode_value()` in Bytes kodiert (UTF-8 fuer Strings, `str(x).encode()` fuer Zahlen) und in den ctypes-Puffer geschrieben. Bei Zugriff wird er dekodiert und als Python-Objekt zurueckgegeben.

Die echte Speicheradresse ist ueber `#adress[var] addr;` auslesbar. Mit `#reflect[addr] var;` kann man die Adresse zurueck in den Wert aufloesen. Als Ausdruck (`if (#adress[var] != 0x0) { … }`) liefert es die Adresse als int — und `0x0` wenn `var` nicht gebunden ist; das ist der idiomatische Guard für `#delete[<vielleicht-weg>]`.

### 2.5 Ownership Model — Reference by Default, `&` for Explicit Copy

**Diese Sektion ist normativ. Jede CSSC-Implementation (Interpreter, nativer Compiler, LSP) MUSS sich exakt an diese Regeln halten.**

#### Grundregel: Alle Übergaben sind Referenzen

Wenn du eine deklarierte Variable in einem Ausdruck verwendest — als Funktionsargument, Container-Element, Vergleichsoperand, Zuweisungsquelle — wird **nichts kopiert**. Der Slot der Variablen wird direkt weitergereicht. Mutiert eine Seite, sieht die andere die Mutation.

```cssc
#stack[int, 32] a = 0;
queue.add(a);     // queue speichert eine REFERENZ auf a
a += 2;           // queue.last() liest jetzt 2
#delete[a];       // queue's Verweis wird via dtor-cascade auch released
```

Dasselbe Prinzip in Kontrollfluss:

```cssc
#stack[int, 32] x = 50;
if (x < 100) { cssc::outln(x); }   // if-body sieht den umgebenden Scope
                                    // -> x referenziert, keine Kopie

{                                   // bare { } ist isolierter Scope
    #req[x] xref;                   // ref-import des äußeren x (Default)
    cssc::outln(xref);              // ok: 50
}                                   // Body-lokale Variablen released

for (int i = 0; i < 10; i += 1) {
    list.add(i);                    // jede Iteration: list bekommt ref auf i
}                                   // i wird hier automatisch released

select (queue) ?n {                 // ?n iteriert ohne Kopie
    handler(n);
}                                   // n wird automatisch released
```

Wichtig zu verstehen:

| Konstrukt | Eigener Scope? | Auto-delete am Ende? |
|---|---|---|
| `{ … }` (bare block) | **Privater Scope** — isoliert, `#req[outer] x;` für Import | Body-lokale Variablen werden am `}` released |
| `for (…) { … }` | Body sieht den umgebenden Scope; `i` ist Loop-eigene Variable | `i` wird gelöscht am `}` |
| `select (…) ?n { … }` | Body sieht den umgebenden Scope | `?n` wird gelöscht am `}` |
| `while (…) { … }` | Body sieht den umgebenden Scope | — |
| Label-Body | Eigener Frame (sieht Object-Member via implizites `this`) | Label-lokale Variablen löschen |
| `#define(name) { … }` | **Privater Scope** — strikt isoliert, `#req` für Imports | Body-lokale Variablen löschen am `}` |
| Object/Sector-Body | Eigener Member-Scope | Member überleben bis `#free[obj]` |

**Hinweis zu `{ … }`-Blöcken**: Im Gegensatz zu C werden bare Blöcke in CSSC als isoliert behandelt — eine Variable die innen deklariert wird, ist außen NICHT sichtbar. Um Werte aus dem umschließenden Scope hereinzubringen, verwende `#req[name] alias;` (Ref-Import) oder `#req[name] &alias;` (Snapshot-Kopie). Beispiele und Details siehe Section 5.4.

#### Explizite Kopie: `&var`

Wenn du explizit eine unabhängige Kopie haben willst (typisch um den Inhalt zu erfassen, der danach mutiert werden soll), benutze den Prefix-Operator `&`:

```cssc
#stack[int, 32] a = 0;
queue.add(&a);    // queue speichert eine KOPIE von a
a += 2;           // queue.last() ist immer noch 0
```

`&` ist eine `cssc::copy(value)`-Operation. Für primitive Typen (`int`, `float`, `bool`) ist `&x` semantisch identisch zu `x`, weil diese eh by-value sind. Für Strings, Vektoren, Maps, Bindings, Objects und Sektoren produziert `&` einen rekursiven Deep-Copy.

#### Caller wins — `#scanp(...) &param;` ist nur HINT

Die ref/copy-Entscheidung trifft **das CALL-SITE**, nicht der Callee. `#scanp(target, type, pos) &param;` (mit `&` auf dem Parameter-Namen) drückt zwar die **Absicht** des Callees aus, dass er eine Kopie erwartet — das **Runtime ignoriert das `&` aber bewusst** und folgt der Call-Site-Syntax.

```cssc
#stack[int, 32] f;
#define(f) {
    #scanp(f, int, 0) &p;   // Callee sagt: "Ich will eine Kopie"
    #delete[p];              // löscht IMMER — egal woher p kam
}

#stack[int, 32] x = 10;

// Variante A — Caller passt by reference (default):
f(x);
cssc::outln(x);     // → "0x0"  (p war eine LIVE-LINK auf x;
                    //           #delete[p] hat x mitgelöscht)

// Variante B — Caller passt explizit eine Kopie:
#stack[int, 32] y = 10;
f(&y);              // & erzwingt cssc::copy(y) am Call-Site
cssc::outln(y);     // → "10"   (p war eine eigene Kopie;
                    //           #delete[p] hat nur die Kopie gelöscht)
```

Diese Regel ist normativ — Interpreter und nativer Compiler verhalten sich identisch. Das LSP-Lint `DELETE_OF_COPY_PARAM_VIA_REF_CALL` warnt am Call-Site, wenn das Risiko besteht (Callee deklariert `&` UND ruft `#delete[]` UND Caller passt by-ref). Die Migration-Lint `REF_BY_DEFAULT_BEHAVIOR_CHANGE` schlägt vor, `&arg` einzufügen, wenn der bisherige Code auf das alte silent-copy-Verhalten gebaut hat.

#### Konstruktor- und Label-Parameter

Constructor-Parameter und Label-Parameter sind ebenfalls Referenzen by default. Das bisherige `*name`-Prefix entfällt — es bleibt als deprecated Alias erhalten, hat aber identische Semantik wie der nackte Name.

```cssc
// Neu — bevorzugte Form:
object Sensor<auto: bus, int: pin> {
    Sensor->bus = bus;       // Member zeigt auf denselben Slot wie bus
}

// Alt — funktioniert weiterhin, aber redundant:
object Sensor<bus, pin> { … }    // v6 Default-Ref (legacy `<*bus, *pin>` deprecated)

// Explizite Kopie eines Parameters:
object Snapshot<&array<int>: buf> {
    // buf ist eine eigene Kopie; Mutation am Originall nicht sichtbar
}
```

#### Transient-Temp-Regel (CSSC v6 — Bare-Literale sind erlaubt)

In CSSC v6 sind bare Literale in Argumentpositionen **erlaubt** — sie werden vom Compiler/Interpreter als **transiente Temps** (Untyped Temps) behandelt und automatisch am Ende des umgebenden Funktions-/Label-Bodies released. Das ist die `scope_push`/`scope_pop`-Klammer (Spec §2.5):

```cssc
cssc::outln("hello");             // ✅ erlaubt — "hello" ist transient,
                                  //    lebt nur fuer diesen Call.
                                  //    LSP zeigt einen HINT (3-Punkt-Underline)
                                  //    als Erinnerung an die Lifetime-Regel.
cssc::outln(2);                   // ✅ erlaubt — int literal ist inline
cssc::outln({1, 2, 3});            // ✅ erlaubt — array literal ist transient
cssc::outln(cssc::uptime());      // ✅ erlaubt — call result ist transient
display.text(0, 32, "boot ok", 0xFFFF, 1);   // ✅ alle Literale sind transient

#stack[string, 64] msg = "hello"; // ✅ deklarierter Owner — Slot adoptiert
cssc::outln(msg);                 // ✅ ref-pass (kein transient)
```

**Die einzige Falle bei Transients**: wenn der Callee den Wert in einen
**outer-lebenden Slot** speichert (z.B. `vec.push_back(arg)`,
`outerSlot = arg`, `mirror &arg;` mit anschliessender Aufbewahrung
ausserhalb), wird der gespeicherte Pointer nach dem Call-Return `0x0`,
weil der `scope_pop` den Heap-Block freigegeben hat. Das LSP-Lint
`TRANSIENT_LITERAL_IN_CALL_ARG` markiert genau diesen Fall pro
Call-Site mit einem HINT-Marker; mit der Quick-Fix `&arg` (am
Call-Site) oder der Empfehlung "deklariere einen Slot" baut man
sich einen sichtbaren Owner.

**Numerische und Bool-Literale** (`42`, `3.14`, `0xFF`, `true`) sind
**inline im CsscVal-Tag** — sie brauchen keinen Heap-Slot und keinen
Auto-Release, daher ist der HINT bei ihnen rein informativ
(Lesbarkeits-Erinnerung).

#### Untyped Temps in Argument-Positionen — Auto-Cleanup-Regel

Das v6-Native-Runtime klammert jeden Label-Methoden- und Function-Body mit `cssc_scope_push` (am Eintritt) und `cssc_scope_pop` (am Return); jede Heap-Allokation, die zwischen diesen beiden landet und keinen named-Slot-Owner findet, faellt mit dem `scope_pop` weg.

```cssc
tick:
    display.text(0, 25, cssc::uptime(), tft::WHITE, 1);
    //                  ^^^^^^^^^^^^^^^
    //                  cssc_float_to_str-Resultat ist ein Temp.
    //                  Lebt nur bis display.text() returnt — danach scope_pop.
```

Bedeutet praktisch:
* Numerische und Bool-Temps sind ohnehin inline im CsscVal-Tag und brauchen kein Cleanup.
* Heap-Temps (String-Concats, `cssc_float_to_str`-Resultate, anonyme `cssc::uptime()`-Strings, bare `"hello"`-Literale in Args) leben fuer die Dauer des umgebenden Funktions-/Label-Bodies und sind danach garantiert frei. Render-Loops mit pro-Tick-Strings lecken nicht.
* Konstruktoren sind die einzige Ausnahme: `cssc_obj_<Type>_ctor` wird vom Emitter explizit NICHT mit `scope_push`/`scope_pop` umklammert, weil seine Allokationen Object-Member-Strings sind, die das ctor-Lebensende ueberstehen muessen.

Der einzige Fehlerfall ist die **Stash-Falle** — wenn der Callee einen
transient-Arg in einen outer-lebenden Slot stashed, wird der stored
Pointer nach Call-Return `0x0`. Das LSP-Lint
`TRANSIENT_LITERAL_IN_CALL_ARG` markiert das pro Call-Site mit HINT.

#### Lifetime und Destruktor-Cascade

Wird ein Container released (Slot delete, Object/Sector free), läuft `cssc_release_internal` rekursiv über alle Member. Jedes referenzierte Heap-Objekt verliert eine Ref. Erreicht ein Objekt Refcount 0, läuft sein `free { }`-Block, dann werden seine Member abgebaut.

```cssc
#heap[array<auto>, 1024] queue;
{
    #stack[int, 32] a = 5;
    queue.add(a);             // queue hält jetzt ref auf a's Slot
                              // a's Refcount: 1 (sein Slot) + 1 (queue's slot) = 2
}                             // a's lokaler Slot pop't → Refcount 1
                              // queue hält den Wert immer noch
cssc::outln(queue[0]);        // 5 — a's data lebt weiter via queue
#delete[queue];               // dtor cascade → queue[0]'s ref released → free
```

Daher die wichtige Konsequenz: **du musst Refs nicht handisch tracken**. Die Refcount-Cascade tut es. Was du tun musst: explizit `#delete[x]` schreiben, wenn der Slot vor dem Scope-Ende sterben soll.

#### `#delmember[…]` — Soft-Wipe (Container bleibt, Inhalt geht)

Manchmal willst du Container-Inhalte loswerden **ohne** den Container selbst zu freen. Beispiel: ein render-Buffer der zwischen Frames re-used wird, oder ein Working-Set das du periodisch leerst aber dessen Allokation du behalten willst.

`#delmember[…]` ist der saubere Weg dafür. Zwei Formen:

| Form | Semantik |
|---|---|
| `#delmember[container];` | Walk über **alle** Entries, release heap-Inhalt jedes Entries. `container.size()` und allocated cap bleiben unverändert. |
| `#delmember[container[idx]];` | Nur Entry an `idx` wird gewiped. Slot bleibt im Container (als null/void), andere Entries unverändert. |

Was "wipe" pro Container-Typ bedeutet:

| Container-Kind | `#delmember[c[i]]` | `#delmember[c]` |
|---|---|---|
| `vector<int|float>` / `array<int|float>` | `c[i] = 0` | alle slots → 0 |
| `map<string, int>` | bucket i: key released, value → 0 | alle buckets gewiped |
| `bind<string, string>` | pair i: beide strings released | alle pairs gewiped |
| `array<bind>` | entry i: heap content (strings) released, entry → null ptr | alle entries gewiped |

Beispiel — periodischer Display-Buffer:

```cssc
#stack[array<bind>, 1024] Buffer;

tick:
    Buffer.push_back({0, 19, "hello"});
    Buffer.push_back({0, 32, "world"});
    render(Buffer);
    #delmember[Buffer];        // wipe content, keep allocation
```

Beispiel — selektives Slot-Clear:

```cssc
select (Buffer) ?i {
    if (i == 0x0) { break; }                  // null-entry → done
    display.text(0, i[0], i[1], tft::WHITE, 1);
    #stack[int, 32] pos = i.pos();
    #delmember[Buffer[pos]];                   // wipe just this entry
    jump;
}
```

`#delmember` ist **idempotent** — wiederholtes Aufrufen auf einem schon gewiped Slot ist ein no-op. Es ist auch **safe** auf null/empty Containern — kein crash, einfach return.

Unterschied zu `#delete` und `#free`:

| Operation | Container | Inhalte |
|---|---|---|
| `#delete[c]` | freed | freed (cascade) |
| `#free[c]` | freed (für Object/Sector) | freed (free-block + cascade) |
| `#delmember[c]` | **bleibt** | freed |

Wer den Container selbst auch loswerden will: erst `#delmember[c]`, dann `#delete[c]`. Aber das ist überflüssig — `#delete[c]` allein released eh die Member via Cascade.

#### Migrationspfad von älterem CSSC-Code

| Alt | Neu | Bedeutung |
|---|---|---|
| `f(*x)` | `f(x)` | War "pass by ref", ist jetzt Default |
| `f(x)` (alt war by-copy) | `f(&x)` | War "pass by value", braucht jetzt explizites `&` |
| `object Foo<*a, *b>` | `object Foo<auto: a, auto: b>` | `*` ist deprecated, bleibt aber als Alias erhalten |
| `#req[X] *Y;` | `#req[X] Y;` | War Ref via `*`, ist jetzt Default. `#req[X] &Y;` ist der neue Snapshot |
| `#req[X] Y;` (alt war Snapshot) | `#req[X] &Y;` | War Snapshot-by-copy, jetzt explizit per `&` markiert |
| `cssc::outln("hi")` | `#stack[string, 8] s = "hi"; cssc::outln(s);` | Bare-Heap-Literal in Arg-Position parse-rejected — Lesbarkeits-Regel (siehe 2.5). Das Runtime würde es safe handhaben (scope_pop), der Parser erzwingt trotzdem einen sichtbaren Slot. |
| `cssc::outln("a " + x)` | `#stack[string, 64] s = "a " + x; cssc::outln(s);` | Concat-Operand "a " ist Bare-Literal in Escape-Pos → gleiche Regel, gleicher Fix |

Der LSP markiert jeden Verstoß als hard error; der native Compiler refused den Build mit präzisen Zeilen-Informationen.

---

## 3. Variablen und Typen

### 3.1 Primitive Typen

| Typ | Beispiel | Beschreibung |
|-----|---------|-------------|
| `int` | `42`, `0xFF`, `0b1010` | Ganzzahl (beliebige Groesse) |
| `float` | `3.14` | Fliesskommazahl — **immer 64-bit double-precision**. `#stack[float, N]` mit N<64 ist ein harter Compile-Error (verhindert silent float32→float64 Denormal-Read-Bug). Minimum-Spec: `#stack[float, 64] x = 3.14;` |
| `string` | `"hello"`, `'world'` | UTF-8 String (Einzel- oder Doppelquotes) |
| `bool` | `true`, `false` | Wahrheitswert |
| `null` | `null`, `0x0` | Nullwert |

### 3.2 Container-Typen

| Typ | Syntax | Beschreibung |
|-----|--------|-------------|
| `array<T>` | `{1, 2, 3}` | Feste Liste |
| `vector<T>` | `[1, 2, 3]` | Dynamische Liste mit STL-Methoden |
| `map<K, V>` | `{'key', 'value'}` | Schluessel-Wert-Paare |
| `bind` | `{a, b; c, d}` *(strukturiert)* oder `{a, b, c}` *(flat)* | Heterogene Zelle-Liste. Strukturierte Form: `;`-getrennte Pairs mit `pair_width` Zellen pro Pair — erlaubt `b[row][col]`-Zugriff. Flache Form: nur `,`-getrennte Zellen — `pair_width = 0`. |

**Bind-Zugriff (kritisch verstehen — sonst hat man `i[1][0] vs i[2]`-Verwirrung):**

Ein bind hat IMMER eine flache Zell-Liste; die `pair_width` bestimmt nur, ob `[row][col]`-Zugriff zugelassen ist:

| Quell-Literal | `pair_width` | Zellen (intern) | `b[N]` | `b[N][M]` |
|--------------|:-:|----------------|--------|-----------|
| `{a, b, c}` (array_literal) | `0` | `[a, b, c]` | Flach: `b[0]=a`, `b[1]=b`, `b[2]=c` | Fehler / degradiert zu `b[N]` (flacher Zugriff) |
| `{a, b; c, d}` (bind_literal, 2-Zellen-Pairs) | `2` | `[a, b, c, d]` | Flach: `b[0]=a`, `b[1]=b`, `b[2]=c`, `b[3]=d` | Strukturiert: `b[row][col] = vals[row * 2 + col]`, also `b[0][0]=a`, `b[1][0]=c`, `b[1][1]=d` |
| `{a, b, c; d, e, f}` (bind_literal, 3-Zellen-Pairs) | `3` | `[a, b, c, d, e, f]` | Flach: `b[N]` mit N=0..5 | Strukturiert: `b[row][col] = vals[row * 3 + col]` |

Beide Zugriffsformen sehen dieselben Daten — sie unterscheiden sich nur darin, ob man die Zellen als 1D-Reihe oder als 2D-Tabelle adressiert. Wer `{y, text; dur, 0}` schreibt, kann sowohl `i[0]` (= y) als auch `i[1][0]` (= dur) lesen.

> **Compiler-Garantie:** alle Pairs eines `bind_literal` müssen die *gleiche* Anzahl Zellen haben (`{a, b; c, d, e}` ist ein Compile-Error). Sonst wäre `row * pair_width + col` mehrdeutig.

**Bind-Methoden (Auswahl):**
- `b.size()` / `b.length()` — Anzahl Pairs (NICHT Zellen). Für `{a, b; c, d}` → `2`.
- `b[i]` — flacher Zugriff auf die i-te Zelle.
- `b[r][c]` — strukturierter Zugriff auf Pair `r`, Spalte `c` (`vals[r * pair_width + c]`).
- `b.push_back(pair)` / `b.pop_back()` — Standard-Container-Ops.
- `b.addmap(m)` — hängt **alle Einträge eines Maps** als Pairs hinten an. Konzeptuell: ein bind ist eine Kette aus Single-Entry-Maps; addmap erweitert die Kette um die Einträge eines Maps (Multi-Entry-Maps werden auf mehrere Pairs verteilt). Akzeptiert auch ein anderes bind als Quelle (Kettenspleißen).

**Beispiel (Render-Frame mit Dauer):**
```cssc
// Strukturierte Form: zwei Pairs, jeweils 2 Zellen.
#heap[bind, 328] frame = {y_pos, displaytxt; duration_ms, 0x0};

// Beide Zugriffsformen lesen dieselbe Frame-Definition:
cssc::outln(frame[0]);       // y_pos       (flach: cell 0)
cssc::outln(frame[1]);       // displaytxt  (flach: cell 1)
cssc::outln(frame[2]);       // duration_ms (flach: cell 2)
cssc::outln(frame[0][0]);    // y_pos       (strukturiert: pair 0, col 0)
cssc::outln(frame[0][1]);    // displaytxt  (strukturiert: pair 0, col 1)
cssc::outln(frame[1][0]);    // duration_ms (strukturiert: pair 1, col 0)
```

### 3.3 String-Operationen

Strings unterstuetzen Zeichenzugriff und Mutation:

```cssc
#stack[string, 128] s = "Hello";
s[0] = 'h';              // Einzelzeichenmutation
cssc::outln(s[1]);        // Zeichenzugriff: 'e'
cssc::outln(s.length());  // 5
cssc::outln(s.upper());   // "HELLO"
```

Verfuegbare Methoden: `.length()`, `.size()`, `.isEmpty()`, `.upper()`, `.lower()`, `.trim()`, `.split(sep)`, `.replace(old, new)`, `.contains(sub)`, `.startsWith(p)`, `.endsWith(p)`, `.indexOf(sub)`, `.charAt(i)`, `.substr(start, len)`, `.reverse()`, `.repeat(n)`, `.padStart(n, ch)`, `.padEnd(n, ch)`, `.toInt()`, `.toFloat()`, `.isDigit()`, `.isAlpha()`

---

## 4. Funktionen

### 4.1 Grundlegendes Modell

In CSSC ist eine Funktion **keine eigenstaendige Entitaet** — sie ist eine Variable, der ein Worker (Callback) zugewiesen wurde. Intern besteht eine Funktion aus:

- `func["value"]` — der letzte Rueckgabewert (oder `null` wenn nie aufgerufen)
- `func["address"]` — die Speicheradresse des Workers

### 4.2 `#define` (einfache Funktion)

```cssc
#stack[int, 32] add;
#define(add) {
    #req[a] a;            // ref-import (v6 default; mutating `a` writes through to outer)
    #req[b] b;            // ref-import (same)
    return a + b;
}
```

- `#define(varName) { body }` weist `varName` einen Worker zu
- Der Body wird in einem **strikt isolierten privaten Scope** ausgefuehrt (Spec §2.5 / §5.4)
- **Outer-Variablen sind NICHT implizit sichtbar** — sie muessen explizit per
  `#req[name] alias;` (Ref-Default) oder `#req[name] &alias;` (Snapshot-Kopie)
  importiert werden. Globale `#stack`-Slots in der gleichen Datei sind ohne
  `#req` nicht erreichbar — das ist Spec-Verhalten, kein Bug, und verhindert
  versehentliches Schreiben in fremde Slots
- Andere `#define`-Funktionen (Top-Level) sind ebenfalls per `#req[funcname] alias;`
  importierbar — danach kann man `alias(arg)` rufen
- `return` gibt einen Wert zurueck (HARD-Abbruch des Bodys; siehe §7.5
  fuer Unterschied zu `mirror`)
- Der Rueckgabewert wird in `func["value"]` gespeichert

### 4.3 `#cdefine` (parametrisierte Funktion)

> **Module-Anforderung**: `#cdefine` gehört zum `def`-Modul. Schreib
> `#include('def');` einmal am Skript-Anfang, sonst meldet der Parser
> einen klaren "missing module" Hinweis. Die Direktive ist nicht core
> wie `#define` / `#redefine` — sie lebt zusammen mit `#fvar`, `#param`,
> `#scanp`, `#scanp_opt`, `#qvar` im `def`-Modul (siehe §10.2).

```cssc
#include('def');

#stack[int, 64] multiply;
#cdefine(multiply, a, b) {
    return a * b;
}
cssc::outln(multiply(3, 4));  // 12
```

### 4.4 `#redefine` (Funktion modifizieren)

```cssc
#redefine(myFunc) {
    cssc::outln("ueberschrieben");
}

#redefine(myFunc) +<0> {
    cssc::outln("am Anfang eingefuegt");
}
```

- Ohne Position: **ueberschreibt** den gesamten Body
- Mit `+<pos>`: **injiziert** Code an Position `pos`
- Aenderungen werden **in-place** am AST vorgenommen — der Worker-Closure sieht die Aenderungen

> **Backend-Hinweis:** `#redefine` ist eine reine Interpreter-Funktion (`cssc run`/`cssc exec`). Das v6-Native-Backend kompiliert Funktionsbodies statisch — eine AST-Mutation zur Laufzeit hat dort keinen Effekt mehr. Für Embedded-Builds entweder Logik mit `if` / `select` schreiben oder per `#cdefine` parametrisieren.

### 4.5 `#scanp` (Parameter auslesen)

```cssc
#include('def');

#cdefine(greet, name) {
    #scanp(greet, string, 0) who;
    cssc::outln("Hallo " + who);
}
```

- `#scanp(source, type, pos) varName;` — liest den Aufrufparameter an
  Position `pos`. **CSSC v6 (Spec §2.5)**: das CALL-SITE bestimmt
  ref vs. copy, NICHT der Callee. `f(x)` bindet `varName` als Ref auf
  die Caller-Slot — `#delete[varName]` im Body invalidiert auch `x`
  beim Caller (Cross-Frame-Delete). `f(&x)` uebergibt eine Kopie —
  `varName` ist ein unabhaengiger Slot.
- `#scanp(source, type, pos) &varName;` — **HINT** (Lesbarkeits-Marker)
  dass der Callee bevorzugt eine Kopie haette. Das Runtime ignoriert
  das `&` aber bewusst — nur das Call-Site entscheidet. Das LSP-Lint
  `DELETE_OF_COPY_PARAM_VIA_REF_CALL` warnt, wenn ein Caller den
  Hinweis ignoriert und ein bare ref uebergibt, obwohl der Body
  `#delete[varName]` ruft. Migration-Quick-Fix: `&arg` am Call-Site
  einfuegen.
- `#scanp(source, type, pos) *varName;` — **Deprecated** Legacy-Form
  fuer Ref. Identische Semantik zu `varName;` ohne Prefix. Neuer
  Code laesst das `*` weg.
- `#fvar`, `#param`, `#cdefine`, `#qvar`, `#scanp_opt`, `#redefine` brauchen
  `#include('def');` einmal am Skript-Anfang — sie leben im `def`-Modul.
  `#scanp` selbst ist core und immer verfügbar.

### 4.6 `#fvar` und `#param`

```cssc
#fvar(int) counter;       // Funktions-Variable (strikt: nur per Aufruf nutzbar)
#param(string) inputStr;  // Parameter-Deklaration (nur per #scanp beschreibbar)
```

---

## 5. Kontrollfluss

### 5.1 Bedingungen

```cssc
if (x > 10) {
    cssc::outln("gross");
} else if (x > 5) {
    cssc::outln("mittel");
} else {
    cssc::outln("klein");
}
```

### 5.2 Schleifen

```cssc
// C-Style
for (int i = 0; i < 10; i = i + 1) {
    cssc::outln(i);
}

// For-In (Werte)
for (val in myList) {
    cssc::outln(val);
}

// For-In mit Index
for (i, val in myList) {
    cssc::outln(i + ": " + val);
}

// While
while (running) {
    cssc::outln("laeuft");
}
```

### 5.3 `select` (Cursor-basierte Iteration)

```cssc
#stack[array<int>, 1024] bytecode = {9, 8, 7, 6, 5, 4, 3, 2, 1, 0x0};

select (bytecode) ?i {
    if (i == 0x0) {
        cssc::outln("Ende");
        return;
    }
    if (i == 1) {
        jump++;     // Cursor +2 (ueberspringe naechstes Element)
    }
    cssc::outln(i);
    jump;           // Cursor +1 (naechstes Element)
}
```

| Befehl | Wirkung |
|--------|---------|
| `jump;` | Cursor +1 |
| `jump++;` | Cursor +2 |
| `!jump;` | Cursor -1 (rueckwaerts) |
| `!jump++;` | Cursor -2 |

- Kein `jump` am Ende des Bodies = Loop beendet
- Cursor ausserhalb der Grenzen = Loop beendet
- `return;` verlasst die gesamte Funktion

> **Backend-Hinweis:** Der v6-Native-Build lowert `select` aktuell nur für `vector<int>` und `array<bind>`. Das obige Beispiel verwendet `array<int>` — für Embedded ändere `#stack[array<int>, …]` zu `#stack[vector<int>, …]` (gleiche Semantik, anderer Container-Kind). Andere iterierbare Container (`array<float>`, `map`, `bind`) landen in Phase 3+ / Phase 4.

#### `?label.pos()` — aktuelle Cursor-Position

Im Body eines `select`-Loops liefert `?label.pos()` den aktuellen Cursor-Index
(0-basiert). Funktioniert in Interpreter und nativem Compiler identisch.

```cssc
#stack[list, 256] n = [10, 20, 30];
select (n) ?i {
    cssc::out("pos=");
    cssc::out(i.pos());      // 0, 1, 2
    cssc::out(" val=");
    cssc::outln(i);
    jump;
}
```

### 5.4 Private Scopes (`{ ... }`)

Bare `{ ... }` auf Statement-Ebene oeffnet einen **isolierten Variablen-Frame**.
Innen deklarierte Variablen leaken nicht nach aussen, und aussere Variablen
sind nicht implizit sichtbar — sie muessen explizit via `#req` importiert
werden.

```cssc
{
    #stack[int, 32] linus = 5;
    cssc::outln(linus);              // 5
}   // linus garantiert zerstoert

{
    #stack[int, 32] linus = 99;     // OK — anderer Scope, kein Konflikt
    cssc::outln(linus);             // 99
}
```

Outer-Variablen importieren via `#req`:

```cssc
#stack[int, 32] outer = 100;
{
    #req[outer] o;
    cssc::outln(o);                  // 100
}
{
    cssc::outln(outer);              // null — keine implizite Sicht
}
```

Anwendungsfall: scopes innerhalb von Funktionen kapseln, kurzlebige
Hilfsvariablen-Blocks abgrenzen, Naming-Kollisionen zwischen logischen
Sequenzen vermeiden.

---

## 6. Sektoren (Namespaces)

### 6.1 Grundstruktur

```cssc
sector Engine {
private:
    #stack[int, 32] fps = 60;
public:
    #stack[string, 128] title = "MyEngine";
    #define(Engine->start) {
        cssc::outln("Engine startet");
    }
} free {
    #delete[fps];
    #delete[title];
};
```

### 6.2 Semantik

- `private:` Mitglieder sind nur innerhalb des Sektors sichtbar
- `public:` Mitglieder sind extern ueber `Sector::member` oder `Sector::func()` erreichbar
- Private Mitglieder geben extern `0x0` (null) zurueck — kein Fehler
- **Scope-Isolation**: Waehrend der Konstruktion wird `_variables` ausgetauscht — der Sektor hat seinen eigenen Variablen-Raum
- **`free {}`**: Pflicht-Aufraeum-Block. Wird bei `#free[Engine]` ausgefuehrt

### 6.3 Generics (Scope-Injection)

```cssc
#stack[int, 32] globalConfig = 42;

sector App<globalConfig> {
    // globalConfig ist hier als Zero-Copy-Referenz verfuegbar
    // (v6 Default; das Legacy `<*globalConfig>` bleibt als Alias erhalten)
} free {};
```

- `<name>` — Zero-Copy-Referenz aus dem aeusseren Scope
- `<&name>` — Deep-Copy aus dem aeusseren Scope
- `<type: name>` — Konstruktor-Parameter

### 6.4 Self-Referenz

```cssc
sector outer {
    sector inner<outer> {
        // inner kann auf outer zugreifen (v6 Default-Ref; legacy
        // `<*outer>` bleibt als Alias erhalten)
    } free {};
} free {};
```

Waehrend der Konstruktion wird ein Live-Platzhalter-Sektor in den Scope injiziert, der dasselbe `_vars`-Dictionary teilt. Innere Sektoren sehen den Eltern-Sektor als echte Referenz.

### 6.5 Deferred Initialization

```cssc
sector Config ?app {
    // wird erst bei #reserve[app] initialisiert
} free {};

#reserve[app];
app::run();
#free[app];
```

---

## 7. Objekte

### 7.1 Grundstruktur

```cssc
object Player {
    #auto[int] Player->hp = 100;
    Player->init();

init:
    cssc::outln("Player erstellt");

takeDamage<int: dmg>:
    Player->hp = Player->hp - dmg;
    if (Player->hp <= 0) {
        call die;
    }

die:
    cssc::outln("Player gestorben");
    destruct;
} free {
    #delete[Player->hp];
};
```

### 7.2 Labels (Instruktionen)

Labels sind benannte Code-Abschnitte innerhalb eines Objekts:

- **Einfach**: `labelName:`
- **Mit Parametern**: `labelName<int: x, string: msg>:`
- **Mit Transfers**: `labelName<outerVar>:` — Zero-Copy aus aeusserem Scope (v6 Default; `<*outerVar>` ist die deprecated Legacy-Form)
- **Ueberladung**: Mehrere Labels mit gleichem Namen aber unterschiedlichen Parametern

```cssc
object Handler {
    process<string: data>:
        cssc::outln("String: " + data);
    process<int: data>:
        cssc::outln("Int: " + data);
} free {};

Handler() h;
h.process("hello");  // -> "String: hello"
h.process(42);        // -> "Int: 42"
```

Die Ueberladungsaufloesung erfolgt zur Laufzeit anhand der Argument-Typen. Exakter Typ-Match bekommt die hoechste Prioritaet.

### 7.3 Instanziierung

```cssc
Player() myPlayer;        // Fuehrt top_level Code aus, gibt self zurueck
myPlayer.takeDamage(30);   // Ruft Label auf
```

### 7.4 Konstruktor-Parameter

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

### 7.5 `call` / `mirror` / `destruct` / `return`

```cssc
object Calculator {
    add<int: a, int: b>:
        mirror a + b;       // RETURN expression — body keeps running
                            //                     for cleanup

    snapshot<data>:         // v6 Default-Ref; `<*data>` ist deprecated
        mirror &data;       // explicit DEEP-COPY return

    shutdown:
        destruct;           // Zerstoert das Objekt, fuehrt free {} aus
} free {};

Calculator() calc;
call add<3, 4> result;      // result = 7
```

#### `mirror` vs `return` — die kritische Unterscheidung

Beide setzen den Rueckgabewert. Der Unterschied liegt in **was danach
passiert** (spec §2.5 Ownership + §7.5):

| Form | Verhalten danach | Verwendung |
|---|---|---|
| `return value;` | **Hard short-circuit.** Body bricht sofort ab. Cleanup-Statements DANACH werden **nicht** ausgefuehrt. | Wenn es nichts mehr zu cleanen gibt. |
| `mirror value;` | **Body laeuft weiter.** Trailing `#delete[copied]` / `#free[X]` / etc. werden noch ausgefuehrt. Default: **REF**-Link zum Quell-Slot. | Wenn der Body Copy-Params oder transiente Allocs besitzt — der einzige sichere Weg, einen Wert zurueckzugeben UND aufzuräumen. |
| `mirror &value;` | Wie `mirror`, aber **Deep-Copy Snapshot** zum Zeitpunkt des `mirror`. Spaetere Cleanup im Body beeinflussen das Outer-Capture nicht. | Wenn der innere Slot direkt nach `mirror` gefreed wird und das Outer trotzdem den Wert behalten soll. |
| `mirror *value;` | **DEPRECATED** Alias für `mirror value;` (war pre-v6 die Ref-Form; `*` ist seit v6 deprecated, der Default ist eh Ref). Wird stumm akzeptiert. | Nur fuer Rueckwaerts-Kompatibilitaet — neuer Code soll das `*` weglassen. |

**Live-Ref-Semantik in Detail** (das ist neu in v6):

```cssc
#stack[int, 32] f;
#define(f) {
    #stack[int, 32] inner = 42;
    mirror inner;           // ← REF-Link: outer ist live-verbunden
    #delete[inner];          // ← inner wird gefreed -> outer = 0x0
}
f() out;
cssc::outln(out);            // → 0   (NICHT 42! ref wurde invalidiert)
```

```cssc
#define(f) {
    #stack[int, 32] inner = 42;
    mirror &inner;           // ← Deep-Copy Snapshot
    #delete[inner];          // ← inner gefreed, outer hat unabhaengige Kopie
}
f() out;
cssc::outln(out);            // → 42
```

```cssc
#define(f) {
    #scanp(f, int, 0) &n;
    #scanp(f, int, 1) &t;
    mirror n + t;            // ← EXPRESSION (kein Slot) → automatisch Snapshot
    #delete[t];
    #delete[n];
}
#stack[int, 32] a = 3;
#stack[int, 32] b = 10;
f(&a, &b) r;                 // → r = 13
```

**Faustregel**: Wenn dein Body nach dem `mirror` noch was cleant, was du
zurueckgibst — schreib `mirror &x;` (Snapshot). Wenn der Cleanup einen
**anderen** Slot betrifft — `mirror x;` (Ref-Default) reicht.

**`destruct;`-Semantik**: Das Schluesselwort fuehrt sofort den `free { }`-Block
aus und beendet den Object-Body sauber. Das aufrufende Host-Script laeuft danach
**weiter** — `destruct` ist kein `exit()`. Wenn alle Cleanup-Statements im
free-Block durchgelaufen sind, kehrt die Kontrolle an die Stelle zurueck, an der
das Object aufgerufen wurde.

**`break;` in einem Object-Label** (ausserhalb von Schleifen) wirkt wie ein
fruehes Return: das Label-Body wird sofort verlassen, ohne das ganze Object zu
zerstoeren. In Schleifen (`for` / `while`) bleibt `break` sein normaler
Schleifen-Abbruch.

- `mirror value;` — Wert zurueckgeben + Body weiterlaufen lassen (Live-REF wenn `value` ein Slot ist)
- `mirror &value;` — Wert zurueckgeben + Body weiterlaufen lassen (Deep-Copy Snapshot)
- `mirror *value;` — DEPRECATED, identisch zu `mirror value;`
- `return value;` — Wert zurueckgeben + Body **sofort abbrechen** (kein Cleanup mehr)
- `destruct;` — Loest den `free {}`-Block aus und markiert das Objekt als tot
- `call label<args> capture;` — Ruft Label auf und faengt Ergebnis

### 7.6 `call` Transfer-Override

```cssc
call myLabel<explicitRef, 42>;   // v6 Default-Ref; `<*explicitRef, …>` ist deprecated
```

`*name` in `call<...>` erzwingt eine explizite Transfer-Referenz anstelle des Auto-Pulls aus dem Scope.

### 7.7 Access Control (via Method)

```cssc
method secure<object> ?cf {
    cf!object.access.private = 1;
    cf!object.access.public = 1;
} do {} free {};

secure ! object Config {
private:
    secret:
        cssc::outln("nur intern");
public:
    start:
        call secret;  // intern: funktioniert
} free {};

Config() c;
c.start();    // -> "nur intern" (intern aufgerufen)
c.secret();   // -> 0x0 (extern: stiller No-Op)
```

---

## 8. Pointer und Referenzen

Seit dem Ownership-Refactor (siehe **2.5**) sind **alle** Argument-Übergaben Referenzen. Du brauchst kein spezielles Syntax für "ich möchte eine Live-Referenz auf X" — der nackte Variablen-Name ist schon eine.

### 8.1 Implizite Referenz (Default)

```cssc
#stack[int, 32] original = 42;
#stack[int, 32] alias = original;     // alias = ref auf original

cssc::outln(alias);     // 42
original = 100;
cssc::outln(alias);     // 100 — alias zeigt auf denselben Slot
```

- Variable-zu-Variable-Zuweisungen sind by-Default Referenzen (kein deepcopy)
- Mutationen am Original sind sofort über jeden Alias sichtbar
- Wird das Original `#delete`d, wird der Alias-Slot zu `0x0` (refcount-cascade)

### 8.2 Explizite Kopie mit `&`

```cssc
#stack[int, 32] original = 42;
#stack[int, 32] snapshot = &original;     // snapshot = unabhängige Kopie

cssc::outln(snapshot);     // 42
original = 100;
cssc::outln(snapshot);     // 42 — snapshot ist unverändert
```

Für primitive Typen (`int`, `float`, `bool`) hat `&` keinen sichtbaren Effekt — sie sind inline und werden eh by-value gehandhabt. Für `string`, `array`, `map`, `bind`, `object`, `sector` produziert `&` einen rekursiven Deep-Copy: Container und alle ihre Elemente.

### 8.3 Legacy `*var` Syntax

Aus Kompatibilitätsgründen wird das alte `*var`-Präfix weiterhin geparst und als **identisch zum nackten Namen** behandelt. Neuer Code sollte das `*` weglassen:

```cssc
// Alt — weiterhin gültig:
queue.add(*item);

// Neu — bevorzugt:
queue.add(item);
```

Der LSP markiert `*`-Verwendungen mit einer "deprecated"-Warning, die du in `cssc.cproject` per `warn_legacy_star = false` stummschalten kannst.

### 8.4 Indexierte Referenzen — `list[i]`

Index-Zugriffe auf Container sind weiterhin Live-Referenzen auf das Slot innerhalb des Containers:

```cssc
#stack[vector<int>, 256] list = [10, 20, 30];
#stack[int, 32] elem = list[1];   // elem = ref auf list[1]
list[1] = 99;
cssc::outln(elem);                  // 99

#stack[int, 32] copy = &list[1];    // explizite Kopie
list[1] = 50;
cssc::outln(copy);                  // 99 — unverändert
```

---

## 8.5 Mutier `%` — geteilte Pagetables

Der `%`-**Mutier** legt einen Wert in einer **geteilten Pagetable** ab — einem
Schlüssel/Wert-Speicher im RAM, den **jedes** CSSC-Runtime im selben Prozess
**und jeder andere CSSC-Prozess** (compiliert wie interpretiert) sehen kann. Er
basiert auf OS-benanntem Shared Memory (flüchtiges RAM, verschwindet wenn das
letzte Runtime endet). Anwendungsfall: einen Rückgabewert über eine Sektor- oder
Prozessgrenze tragen, an der ein normaler Slot `0x0` läse.

| Form | Bedeutung |
|------|-----------|
| `%val` | Legt `val` in der **öffentlichen** Pagetable an; ergibt die 64-Bit-Adresse |
| `%<id>val` | Legt in einer **privaten** Pagetable an, adressiert per `id` (int, auch dynamisch) |
| `%addr = n` | **Schreibt** `n` in den Eintrag an Adresse `addr` |
| `#DEFINE %addr name;` | **Aliasiert** eine Adresse auf `name` — Lesen/Schreiben von `name` trifft die Pagetable |
| `return %val;` | Gibt aus einer (privaten) Funktion die **Adresse** zurück (bereits nutzbar, kein `%` nötig) |
| `#pdelete[addr];` | **Gibt** den Eintrag an `addr` frei (Alias-Name oder Adresse) |

```cssc
#stack[int, 64] a = 42;
#stack[int, 64] addr = %a;          // 42 in die öffentliche Pagetable -> Adresse
#DEFINE %addr geteilt;              // geteilt == der Eintrag an addr
cssc::outln(geteilt);               // 42
geteilt = 100;                      // schreibt die Pagetable
%addr = 7;                          // dito, direkt über die Adresse
cssc::outln(geteilt);               // 7
#pdelete[addr];                     // Eintrag freigeben

#stack[int, 64] id = 376128937;
%<id>99;                            // 99 in eine private Pagetable (per id) veröffentlichen
```

Werte sind 64-Bit. Der Interpreter gibt beim Lesen den ursprünglichen Typ zurück
(int/float/bool), der Compiler liefert das rohe i64-Wort (RAW) — für `int`
identisch, `float`/`bool` müsste man im Compiler selbst reinterpretieren. Adressen
sind pro Pagetable fortlaufend; eine private `id` teilt sich jedes Runtime, das
exakt dieselbe `id` verwendet.

---

## 9. Das Method-System (Metaprogrammierung)

### 9.1 Grundstruktur

```cssc
method Guard<string> ?base {
    base!size.value *SizeVal;
    base!value *Value;
    base!constraints.max_length = 10;
} do {
    cssc::outln("Mutation: " + Value);
} free {
    cssc::outln("Guard freigegeben");
};

Guard ! #stack[string, 256] name = "Hello";
name = "World";     // -> do {} feuert: "Mutation: World"
#delete[name];      // -> free {} feuert: "Guard freigegeben"
```

### 9.2 Wie Methods funktionieren

Eine Method definiert **zusaetzliches Verhalten** fuer eine Variable:

1. **Deklarationsblock `{}`**: Bindet Introspektions-Eigenschaften an lokale Namen und setzt Constraints
2. **`do {}`-Block**: Wird bei **jeder Mutation** ausgefuehrt (Zuweisung, Loeschung, Kopie, Index-Aenderung)
3. **`free {}`-Block**: Wird beim `#delete` ausgefuehrt

### 9.3 Anwendung auf verschiedene Typen

```cssc
method Name<string> ?base { ... }              // Nur auf Strings
method Name<sector> ?base { ... }              // Nur auf Sektoren
method Name<object> ?base { ... }              // Nur auf Objekte
method Name<int> ?base { ... }                 // Nur auf Integer
method Name<array<auto>> ?base { ... }         // Auf Arrays (mit Generics)
method Name<auto> ?base { ... }                // Auf alles
```

### 9.4 Scope-Parameter

```cssc
#auto[string] sdkVersion = "v2.0";

method Codespace<sector, *sdkVersion> ?main {
    main!name *VarName;
} do {
    cssc::outln("SDK: " + sdkVersion);
} free {};

Codespace ! sector App { ... } free {};
```

- `name` in `<type, name>` injiziert eine aeussere Variable per Referenz in den Method-Scope (v6 Default; das alte `<type, *name>` bleibt als Alias erhalten)
- Aenderungen im `do {}`-Block werden nach Ausfuehrung zurueckgeschrieben

### 9.5 Mutation-Events

| Event | Trigger |
|-------|---------|
| `assign` | `var = newValue` |
| `copied` | `otherVar = var` (Quellseite) |
| `passed` | `func(var)` (Argument) |
| `returned` | `return var` |
| `delete` | `#delete[var]` |
| `index_assign` | `var[i] = val` |
| `dot_assign` | `var.key = val` |

### 9.6 Introspection (`base!property`)

#### Universal (alle Typen)

| Eigenschaft | Beschreibung |
|-------------|-------------|
| `value` | Aktueller Wert |
| `value.type` | Typname |
| `value.size` | Groesse in Bits |
| `address` | Speicheradresse (Hex) |
| `capacity.value` | Allokierte Kapazitaet in Bits |
| `size.value` | Genutzte Groesse in Bits |
| `name` | Variablenname |
| `line` | Zeilennummer der Deklaration |
| `region` | Speicherregion (stack/heap/auto) |
| `mirror` | Selbstreferenz (Zero-Copy) |
| `interaction.type` | Letzter Mutations-Typ |

#### Constraints (Wert-Validierung)

| Eigenschaft | Beschreibung |
|-------------|-------------|
| `constraints.min` | Minimaler Zahlenwert |
| `constraints.max` | Maximaler Zahlenwert |
| `constraints.min_length` | Minimale Laenge (Strings/Listen) |
| `constraints.max_length` | Maximale Laenge |
| `constraints.regex` | Regex-Muster (Strings) |
| `constraints.allowed` | Whitelist-Array |
| `constraints.forbidden` | Blacklist-Array |
| `constraints.predicate` | Eigene Validierungsfunktion |

Bei Verstoss wird ein `#panic`-Fehler geworfen.

#### Hooks (Lifecycle-Callbacks)

| Eigenschaft | Beschreibung |
|-------------|-------------|
| `hooks.before_assign` | Vor Zuweisung (empfaengt `new_val`, `old_val`) |
| `hooks.after_assign` | Nach Zuweisung |
| `hooks.before_delete` | Vor Loeschung |
| `hooks.after_delete` | Nach Loeschung |
| `hooks.before_copy` | Vor Kopie |
| `hooks.after_copy` | Nach Kopie |
| `hooks.before_call` | Vor Funktionsaufruf (nur fuer Funktionen) |
| `hooks.after_call` | Nach Funktionsaufruf |

Hooks werden per Funktionsreferenz gesetzt: `base!hooks.before_assign = myHookFunc;`

#### Storage-Kontrolle

| Eigenschaft | Beschreibung |
|-------------|-------------|
| `storage.locked` | Immutable nach erster Zuweisung |
| `storage.encrypted` | XOR-Verschluesselung im Speicher |
| `storage.encrypt_key` | Verschluesselungsschluessel (0-255) |
| `storage.alignment` | Byte-Alignment |
| `storage.encoding` | Text-Encoding ("utf-8", "ascii") |

#### Sektor/Objekt-Kontrolle

| Eigenschaft | Beschreibung |
|-------------|-------------|
| `members.list` | Liste aller Mitglieder |
| `members.count` | Anzahl der Mitglieder |
| `members.add` | Mitglied dynamisch hinzufuegen |
| `members.remove` | Mitglied entfernen |
| `labels.list` | Liste aller Labels (Objekte) |
| `labels.count` | Anzahl der Labels |
| `labels.add` | Label dynamisch hinzufuegen |
| `labels.remove` | Label entfernen |
| `object.access.private` | Private-Enforcement aktivieren |
| `object.access.public` | Public-Enforcement aktivieren |
| `instance.singleton` | Nur eine Instanz erlaubt |

---

## 10. Module

### 10.1 Einbinden

```cssc
#include('video') vid;
#include('keyboard') kb;
#include('os') os;
```

**Wichtig**: Jedes `#include` erzeugt einen Modul-Sektor. Der Host-Script muss diesen am Ende mit `#free[alias]` freigeben.

### 10.2 Verfuegbare Module

| Modul | Beschreibung |
|-------|-------------|
| `cssc.dll` | DLL-Loading und Native-Calls |
| `cssc.ini` | INI-Dateien lesen/schreiben |
| `cssc.paths` | Pfad-Manipulation |
| `cssc.env` | Umgebungsvariablen |
| `cssc.sys` | Systeminformationen |
| `cssc.io` | Datei-I/O |
| `cssc.fastif` | Einzeilige Bedingungen |
| `def` | Erweiterte Funktionsdefinitionen (`#fvar`, `#param`, `#cdefine`, `#qvar`, `#scanp`, `#scanp_opt`) |
| `cssc.math` | Mathematik (Trigonometrie, Logarithmen) |
| `cssc.binary` | Binaer-I/O |
| `stdio` | Standard-File-I/O |
| `sizes` | Empfohlene Bit-Groessen |
| `cssl` | CSSL-Interop |
| `matrix` | 2D-Pixel-Matrix |
| `video` | Native Video-Fenster (Win32/X11) |
| `video.sprite` | Sprites, Sprite-Sheets, Animationen (BMP-Loader) — siehe 10.4k |
| `video.tilemap` | Tilemaps + Camera + Solid-Tile-Kollision — siehe 10.4l |
| `video.font` | Bitmap-Fonts + Text-Metriken + Text-Wrapping — siehe 10.4m |
| `keyboard` | Echtzeit-Tastatur (GetAsyncKeyState) |
| `mouse` | Maus-Input |
| `sound` | Native Audio (winmm.dll) |
| `asyncthreads` | Threading und Daemon-Prozesse |
| `serialcommunication` | IPC ueber virtuelle Ports |
| `os` | Betriebssystem-Zugriff (Windows/Linux) |
| `sys.console` / `console` | Native Konsole + sync (siehe 10.3) |
| `cssc.peek` | Look-ahead/Window-Funktionen fuer Container |
| `cssc.sidepackagetools` | Paket-Registry fuer wiederverwendbare Module |
| `openai` | OpenAI Chat-Completions, Embeddings (siehe 10.4) |
| `retrogadgets` | Retro Gadgets `gdt`-API (CPUs, VideoChip, AudioChip, Knobs, Buttons, …) |
| `devdebug` | Debug-only Diagnostik (`#debug`, `#trace`, `dev::stdout`) — siehe 10.4d |
| `stdgrace` | Graceful Error Handling (`grace::catch`, `#catch`) — siehe 10.4e |
| `gipeo` | GPIO + I2C/SPI/UART/ADC/PWM/Timer für ESP32/ESP8266/Arduino/Raspberry — siehe 10.4g |
| `allocwatcher` | Live Allocation-Visualizer (GUI + Snapshots) — siehe 10.4h |
| `tft` | TFT/OLED Displays (SSD1306/ILI9341/ST7789/...) mit Win32-Emulator + nativem Output — siehe 10.4i |
| `network.http` | HTTP/HTTPS Client (urllib/WinHTTP/ESP-HTTP/ESP8266HTTPClient/libcurl) — siehe 10.4j |

### 10.3 `sys.console` / `console` — Native Konsole + Sync

`#include('console');` und `#include('sys.console');` referenzieren dasselbe
Modul. Output ist **disjoint** von `cssc::outln(...)` — `cons.out(...)` taucht
nie im Haupt-stdout auf und umgekehrt.

```cssc
#include('console');
#include('devdebug') dev;

#console[80, 25] con;
con.cursor_col(0x00FF00);
con.cout("Hello console");
con.cursor_set(5, 2);
con.out("at line 5, col 2");

// Tail-Forwarding: jede #debug-Nachricht erscheint live als [dev] <msg>
con.sync('dev', *dev::stdout);
#debug('first');                  // → [dev] first im Console-Fenster
#debug('second');                 // → [dev] second
con.desync('dev');                // stop forwarding (drained pending entries)
con.close();
```

| Methode | Beschreibung |
|---------|-------------|
| `con.out(text)` | Schreibt am Cursor mit aktueller Farbe (this console only) |
| `con.cout(text)` / `outln(text)` | Wie `out()`, plus newline |
| `con.clear()` / `clear_all()` | Leert den gesamten Buffer |
| `con.clear_line(n)` | Leert eine Zeile |
| `con.cursor_col(0xRRGGBB)` | Setzt Vordergrundfarbe |
| `con.cursor_set(line, col)` | Cursor an absolute Position |
| `con.cursor_pos(p)` | Horizontale Position, p ∈ [-1, 1] |
| `con.getLine()` / `cursor_get_line()` | Liest die aktuelle Zeile |
| `con.cursor_at()` | Liefert `[line, col]` |
| `con.sync(tag, *container)` | Tail-forward einer list-like in die Console |
| `con.desync(tag)` | Stoppt Sync; drained pending Entries vorher |
| `con.close()` | Gibt die Konsole frei |

**`.sync(tag, container)` Semantik:**
- Container ist by-reference (jede `len()`-bare + indexierbare Struktur).
- Daemon-Thread pollt alle ~50ms und emittiert neue Einträge als `[tag] <entry>`.
- Tail, kein Replay: bei attach wird `last_len = current_len` gesetzt — vorhandene Einträge spammen nicht.
- Re-Sync mit demselben tag ersetzt sauber.

**Eigenes Fenster vs. geteilt:**
- Wenn der Prozess **schon** an einer Console hängt (`cssc run` aus PowerShell), spawnt der Interpreter einen Subprocess mit `CREATE_NEW_CONSOLE` — du bekommst ein **echtes separates Fenster**.
- Falls kein Parent-Console (GUI-Build), wird `AllocConsole()` für das eigene Fenster benutzt.

**`--no-console` Flag** (auf `cssc run` und `cssc build`):
- Downgraded `#console[…]`-Fenster zu einer stderr-präfixten Senke (`[console] …`-Zeilen).
- `cssc::outln`-Pfad bleibt unverändert.
- Nützlich für CI / headless Runs ohne Tk/Win32-Dependencies.

Auf Nicht-Windows fällt der Output auf stdout zurück.

### 10.3b `sys` — Kommandozeilen-Argumente

`#include('sys') sys;` macht die CLI-Args des aktuellen Skripts zugänglich. Funktioniert identisch im Interpreter und im nativen Compile-Pfad. Argumente kommen aus:

* `cssc run script.cssc arg1 arg2 ...` → alles nach dem Skriptpfad
* Doppelklick auf eine `.cssc` mit `cssc.exe`-Assoziation → keine Args
* Eingebettet (`cssl::cssc(...)`) → über die Aufrufer-API gesetzt

```cssc
#include('sys') sys;

#stack[int, 32] n = sys::argc;
if (n == 0) {
    cssc::outln("Usage: script.cssc <name> [age]");
    cssc::exit(1);
}
cssc::outln("Hallo " + sys::arg(0));
if (sys::has_arg(1)) {
    #stack[int, 32] age = sys::arg_int(1);
    cssc::outln("Alter: " + age);
}
```

| Symbol | Typ | Bedeutung |
|---|---|---|
| `sys::args` | `array<string>` | Komplette Args-Liste, ohne den Skriptpfad |
| `sys::argc` | int | `len(args)` |
| `sys::arg(i)` | string \| null | Wert an Index `i`; null bei out-of-bounds |
| `sys::has_arg(i)` | bool | `0 <= i < argc` |
| `sys::arg_int(i)` | int | Wert geparst als int (0 wenn nicht parsbar) |
| `sys::arg_float(i)` | float | als float |
| `sys::arg_bool(i)` | bool | `"true"`/`"1"`/`"yes"` → true, sonst false |

**Alternative (knapper)**: das `cssc::`-Namespace exponiert `cssc::args()` als Liste — kein `#include` nötig. Gleicher Inhalt wie `sys::args`:

```cssc
#stack[array<string>, 1024] all = cssc::args();
cssc::outln(all);   // ["foo", "bar"]
```

**`#sysarg[type, index] var;`** — Sugar für "deklariere `var` mit dem `i`-ten Arg, type-checked + stack-allocated":

```cssc
#sysarg[int, 0] port;        // err if argc < 1 or arg[0] isn't int
#sysarg[string, 1] hostname; // err if argc < 2
```

### 10.4 `openai` — Chat-Completions & Embeddings

Per-Instance-Client: jede Konfiguration (API-Key, Modell, System-Prompt,
Base-URL, Timeout) lebt **auf der Instanz** — keine globalen Singletons,
mehrere parallele Clients sind erlaubt.

```cssc
#include('openai') ai;

ai::OpenAIClient("sk-...") MyAI;
MyAI.set_model("gpt-4o");
MyAI.set_system("Du bist ein knapper Assistent. Antworte in einem Satz.");

#stack[string, 8192] reply = MyAI.chat("Was ist 2+2?");
cssc::outln(reply);
#delete[reply];

#free[ai];
```

#### Konstruktor (im `ai::`-Namespace)

| Form | Beschreibung |
|------|-------------|
| `ai::OpenAIClient(api_key, model?, base_url?, timeout?) MyAI;` | Primaer-Konstruktor |
| `ai::Client(api_key, ...)` | Alias |
| `ai::connect(api_key, ...)` | Alias (fluent style) |

Wird `api_key = ""` uebergeben, liest der Konstruktor `OPENAI_API_KEY` aus der
Umgebung. Kein Argument gleichbedeutend.

#### Methoden auf der Instanz

| Methode | Beschreibung |
|---------|-------------|
| `.chat(prompt, model?) -> string` | One-shot User-Prompt; nutzt `set_system()` falls gesetzt |
| `.completion(messages, model?) -> string` | Volle Chat-Completion. `messages` = Liste aus `bind`-Paaren `{role, content}` |
| `.embedding(text, model?) -> list<float>` | Vector-Embedding (Default `text-embedding-3-small`). Nur Interpreter. |
| `.set_model(name)` | Default-Modell auf dieser Instanz |
| `.set_system(text)` | Persistenter System-Prompt fuer alle `chat()`-Aufrufe |
| `.set_base_url(url)` | Alternativen Endpoint setzen |
| `.set_timeout(seconds)` | HTTP-Timeout (Default 60) |
| `.model() -> string` | Aktuelles Modell |
| `.has_key() -> bool` | True iff API-Key vorhanden |
| `.list_models() -> list<string>` | Verfuegbare Modelle (Interpreter only) |

#### Messages mit `bind` (kein JSON noetig)

`.completion()` akzeptiert eine Liste von `bind`-Paaren — CSSCs Key-Value-Typ.
JSON-Serialisierung passiert intern, transparent fuer den User.

```cssc
#stack[bind, 256] sys_msg  = bind { 'role' => 'system',  'content' => 'You are a helpful assistant.' };
#stack[bind, 256] user_msg = bind { 'role' => 'user',    'content' => 'Tell me a joke.' };
#stack[list<bind>, 1024] msgs = [sys_msg, user_msg];

#stack[string, 8192] reply = MyAI.completion(msgs);
cssc::outln(reply);
```

Native-Compiler liest die Binds direkt aus dem Vector und encodiert ohne
Heap-Allokation einer JSON-Datenstruktur — nur ein lineares Schreiben in den
Request-Body-Puffer.

#### Native vs. Interpreter

| Methode | `cssc run` | `cssc build` |
|---------|:---------:|:------------:|
| `.chat`, `.completion` | ✓ (SDK / urllib) | ✓ (WinHTTP) |
| `.set_model`, `.set_system`, `.set_base_url`, `.set_timeout` | ✓ | ✓ |
| `.model`, `.has_key` | ✓ | ✓ |
| `.embedding`, `.list_models` | ✓ | nicht eingebaut |

Im nativen Build wird gegen `-lwinhttp` gelinkt — kein externes SSL/HTTPS-
Toolkit, keine Python-Runtime im Binary. Reine Windows-Systembibliotheken.

#### Beispiel — kompilierte CLI-App

```cssc
#include('openai') ai;

ai::OpenAIClient("") MyAI;        // API-Key aus OPENAI_API_KEY env

#stack[string, 1024] q = cssc::input("Frage: ");
#stack[string, 8192] a = MyAI.chat(q);
cssc::outln(a);

#delete[q];
#delete[a];
#free[ai];
```

```powershell
cssc build assistant.cssc -o assistant
.\assistant.exe
```

### 10.4b `retrogadgets` — Retro Gadgets `gdt`-API

Mirror der echten Retro-Gadgets-API von `docs.retrogadgets.game`. Jede
Property, jede Methode und jeder Slot-Bereich entspricht exakt dem,
was die Module-Dokumentation des Spiels beschreibt.

```cssc
#include('retrogadgets') gdt;

gdt::VideoChip0::Clear(gdt::Color::black);
gdt::VideoChip0::DrawLine(gdt::Vec::vec2(0,0), gdt::Vec::vec2(63,63), gdt::Color::red);
gdt::VideoChip0::RenderOnScreen();

gdt::AudioChip0::Play(sample, 0);
gdt::FlashMemory0::Save({"score": 100});

#stack[float, 64] knob_val = gdt::Knob0::Value;     // -100..100
```

#### System-Chips (Slots `0..3`)

| Modul | Properties | Methoden |
|-------|-----------|----------|
| `CPUn` | `Source`, `Time`, `DeltaTime`, `EventChannels` | — |
| `VideoChipn` | `Mode`, `Width`, `Height`, `RenderBuffers`, `TouchState/Down/Up/Position` | `Clear`, `SetPixel`, `DrawPointGrid`, `DrawLine`, `DrawCircle`/`Fill`, `DrawRect`/`Fill`, `DrawTriangle`/`Fill`, `DrawSprite`, `DrawCustomSprite`, `DrawText`, `RasterSprite`, `RasterCustomSprite`, `DrawRenderBuffer`, `DrawCustomRenderBuffer`, `RasterRenderBuffer`, `RasterCustomRenderBuffer`, `SetPixelData`, `BlitPixelData`, `RenderOnScreen`, `RenderOnBuffer`, `SetRenderBufferSize` |
| `AudioChipn` | `ChannelsCount`, `Volume` | `Play`, `PlayScheduled`, `PlayLoop`, `PlayLoopScheduled`, `Stop`, `Pause`, `UnPause`, `IsPlaying`, `IsPaused`, `GetPlayTime`, `SeekPlayTime`, `Set/GetChannelVolume`, `Set/GetChannelPitch`, `GetSpectrumData`, `GetDspTime` |
| `FlashMemoryn` | `Size`, `Usage` | `Save(table)`, `Load() -> table` |
| `GamepadChipn` | `GamepadIndex`, `IsActive` | `GetButton`, `GetAxis`, `GetButtonAxis` |
| `KeyboardChipn` | — | `GetButton`, `GetButtonAxis` |
| `Wifin` | `AccessDenied`, `AudioStreams` | `WebGet`, `WebPutData`, `WebPostData`, `WebPostForm`, `WebCustomRequest`, `WebGetAudioStream`, `WebAbort`, `Get(Up\|Down)loadProgress`, `ClearCookieCache`, `ClearUrlCookieCache` |
| `Serialn` | `ReceiveMode`, `Port`, `IsActive`, `BaudRate`, `DataBits`, `Parity`, `StopBits` | `WriteInt*/UInt*/Float*`, `Write`, `Print`, `Println`, `GetAvailablePorts` |
| `MagneticConnectorn` | `ButtonState`, `IsConnected`, `AttachedConnector` | — |

#### Input-Module (Slots `0..7`)

| Modul | Properties |
|-------|-----------|
| `AnalogStickn` | `X` (-100..100), `Y` (-100..100), `InputSourceX/Y` |
| `DPadn` | `X`, `Y` (diskret -100/0/100), `InputSourceX/Y` |
| `Keypadn` | `ButtonsState[col][row]`, `ButtonsDown[col][row]`, `ButtonsUp[col][row]`, `ButtonsInputSource[col][row]` |
| `Knobn` | `Mode`, `Value`, `DeltaValue`, `IsMoving` |
| `LedButtonn` | `ButtonState`, `ButtonDown`, `ButtonUp`, `InputSource`, `LedState`, `LedColor` |
| `ScreenButtonn` | `ButtonState`, `ButtonDown`, `ButtonUp`, `InputSource`, `VideoChip`, `Offset`, `Width`, `Height` |
| `Slidern` | `Value` (0..100), `IsMoving` |
| `Switchn` | `State`, `InputSource` |
| `Webcamn` | `RenderTarget`, `AccessDenied`, `IsActive`, `IsAvailable`, `GetRenderBuffer()` |

#### Output-Module (Slots `0..7`)

| Modul | Properties + Methoden |
|-------|----------------------|
| `AnalogGaugen` | `Value` (0..100) |
| `Lcdn` | `Text` (Zeile 2 ab Zeichen 17), `BgColor`, `TextColor` |
| `Ledn` | `State` (bool), `Color` |
| `LedMatrixn` | `States[col][row]`, `Colors[col][row]` |
| `LedStripn` | `States[i]`, `Colors[i]` |
| `Screenn` | `VideoChip`, `Offset`, `Width`, `Height` |
| `SegmentDisplayn` | `States`, `Colors`, `ShowDigit(group, digit)`, `SetDigitColor(group, color)` |
| `Speakern` | `State` |

#### Singletons (kein Slot-Index)

| Modul | API |
|-------|-----|
| `ROM` | `User.{Assets,SpriteSheets,Codes,AudioSamples}`, `System.*` |
| `PowerButton` | `ButtonState` |
| `RealityChip` | `Cpu`, `Ram`, `Network`, `LoadedAssets`, `GetDateTime`, `GetDateTimeUTC`, `LoadAudioSample`, `LoadSpriteSheet`, `UnloadAsset`, `ListDirectory`, `GetFileMetadata` |
| `SecurityChip` | (Asset-Permissions, aktuell ohne Code-API) |

#### Convenience-Helpers

In Retro Gadgets sind diese tatsächlich top-level Globals — wir surfacen sie
zusätzlich unter `gdt::` damit der Namespace-Stil konsistent bleibt:

- `gdt::Color::Color(r,g,b)`, `gdt::Color::ColorRGBA(r,g,b,a)`, `gdt::Color::ColorHSV(h:0-360, s,v:0-100)`, plus Konstanten `black`, `blue`, `clear`, `cyan`, `gray`, `green`, `magenta`, `red`, `white`, `yellow`
- `gdt::Vec::vec2(x,y)`, `gdt::Vec::vec3(x,y,z)`
- `gdt::Multitool::log`, `print`, `logWarning`, `logError`, `write`, `writeln`, `setFgColor`, `setBgColor`, `resetColors`, `setCursorPos`, `clear`, `clearToEndLine`

#### Pipelines

- `cssc run`: Interpreter mit No-Op-Stubs + realistischen Defaults — perfekt zum lokalen Testen ohne Retro-Gadgets-Host.
- `cssc convert script.cssc --luau`: emittiert die Calls 1:1 als Lua, ready für Retro Gadgets.

### 10.4c `def` — Erweiterte Funktionsdefinitionen

```cssc
#include('def');

#define(sum) {
    #scanp(sum, int, 0) x;
    #scanp(sum, int, 1) y;
    #scanp_opt(sum, int, 2) bonus;     // optional — null wenn fehlend
    if (bonus == null) { bonus = 0; }
    #qvar(int, x + y + bonus) result;
    return result;
}

sum(10, 20)     a;     // a = 30  (bonus null → 0)
sum(10, 20, 5)  b;     // b = 35
```

| Direktive | Zweck |
|-----------|-------|
| `#fvar(type) name;` | Deklariere eine typisierte Funktions-Variable (Return-Type) |
| `#param(type) name;` | Deklariere einen typisierten Parameter für das nächste `#cdefine` |
| `#cdefine(func, p1, p2) { … }` | Vollständige Callback-Definition mit benannten Parametern |
| `#qvar(type, expr) name;` | Quick-Variable aus einem Ausdruck |
| `#scanp(func, type, pos) name;` | **Pflicht-Parameter** aus den Call-Args lesen |
| `#scanp_opt(func, type, pos) name;` | **Optionaler Parameter** — fehlt der Call-Arg, wird `name` `null`, kein Error |

**Unterschied `#scanp` vs `#scanp_opt`**:

```cssc
#scanp(sum, int, 2) required;       // erwartet IMMER 3+ args; Default-Klausel via "= expr" optional
#scanp_opt(sum, int, 2) optional;   // explizit als optional markiert, fehlt → null
```

Beide akzeptieren auch eine Default-Wert-Klausel:
```cssc
#scanp_opt(sum, int, 2) bonus = 100;   // null wird durch 100 ersetzt
```

`#scanp_opt` löst **nur dann** auf null auf, wenn weder ein Call-Arg noch ein Default da war — perfekt für variadic-style APIs wo trailing args sich aufbauen.

### 10.4d `devdebug` — Debug-only Diagnostik

```cssc
#include('devdebug') dev;

#debug('user logged in: ' + name);   // silent ohne --debug
#trace(myfunc);                      // tracet jeden Aufruf von myfunc

// Direktindex-Zugriff auf den persistenten stdout-Container:
cssc::outln(dev::stdout[0]);
```

`#debug(msg)` und `#trace(funcName)` sind auf stderr **stumm**, solange das Script ohne `--debug` läuft. Aber: jede `#debug`-Nachricht wird in den **immer aktiven** Container `dev::stdout` (`list<string>`) angehängt — d.h. ein `#console`-Sync (siehe 10.3) sieht den vollen Stream auch ohne CLI-Flag.

**Aktivierung:**
- Interpreter: `cssc run script.cssc --debug`
- Native:     `cssc build script.cssc --debug -o app`

Ohne `--debug` ist der stderr-Pfad ein einzelner If-Check — praktisch kostenlos. Der List-Append läuft trotzdem, damit der Console-Sync-Use-Case unabhängig von der CLI-Flag funktioniert.

### 10.4e `stdgrace` — Graceful Error Handling

```cssc
#include('stdgrace') grace;

// Funktional — gibt [value, error] zurück
grace::catch(myFunc) result;
if (result[1] != 0x0) {
    cssc::outln('failed: ' + result[1]);
} else {
    cssc::outln('ok: ' + result[0]);
}

// Block-Form — ?caller wird an die Fehlermeldung gebunden
#catch (riskyFunc()) ?c {
    if (c == 'RuntimeError') {
        cssc::outln('recovered: ' + c);
    }
}

// Expressions sind erlaubt:
#catch (obj.method(arg)) ?err { cssc::outln('caught: ' + err); }
#catch (1 / 0)            ?err { cssc::outln('div by zero: ' + err); }
```

`grace::catch(callback, sink?)` gibt **immer** eine 2-elementige Liste zurück:
- `[returned_value, 0x0]` bei Erfolg
- `[0x0, "<ErrType>: <msg>"]` bei Fehler

Ein optionales zweites Argument (`sink`) wird zusätzlich geschrieben — callable, CsscPointer, dict oder list werden alle akzeptiert.

`#catch (executable) ?caller { body }` führt den Ausdruck aus; bei Fehler wird `caller` an den formatierten Fehlerstring gebunden und der Body läuft. Bei Erfolg: Body wird übersprungen. Native-Compiler nutzt `setjmp`/`longjmp` — `cssc_panic`/`cssc_error` springen zum aktiven Catch-Frame statt abzubrechen.

### 10.4f `asyncthreads` — Threading & Daemon-Prozesse

```cssc
#include('asyncthreads');

#stack[int, 32] hits = 0;
#define(beat) {
    #req[hits] h;      // h = TRUE reference (v6 Default), mutiert hits direkt.
                       // Legacy `#req[hits] *h;` ist deprecated aber bleibt
                       // als Alias erhalten.
    h += 1;
}
#daemon[beat];          // Spawnt beat in einem Hintergrund-Thread, looped
cssc::sleep(220);       // ~4 Ticks bei 50ms-Kadenz
#killdaemon[beat];      // Setzt should_stop, Thread terminiert kooperativ
cssc::outln('hits=' + hits);
```

**Daemon-Semantik (Interpreter & Native):**
- `#daemon[fn]` ruft `fn()` **wiederholt** in einem Hintergrund-Thread auf, mit **50ms-Kadenz** zwischen Iterationen (yields GIL/Scheduler, bounded `#killdaemon`-Latency).
- Errors werden auf stderr ausgegeben als `[daemon-<name>] <Type>: <msg>` — nicht mehr stillschweigend geschluckt. Nach **3 aufeinanderfolgenden Fehlern** gibt der Daemon auf, um Endlos-Spam zu vermeiden.
- `#killdaemon[fn]` setzt `should_stop=1`; der nächste Iterations-Check bricht die Schleife.

> **Backend-Hinweis:** Threading-Direktiven (`#daemon`, `#killdaemon`, `#thread`) sind im v6-Native-Backend **nicht implementiert** und produzieren einen CIR-Lower-Fehler. Auf ESP32 ist ein FreeRTOS-Mapping geplant (Phase 6); ESP8266 hat kein OS-Threading. Bis dahin: kooperatives Multitasking via `tick:`-Loops + Zustandsmaschinen — das deckt fast alle Embedded-Use-Cases. Für Host-Builds funktionieren die Direktiven weiterhin über den `--gcc`-Legacy-Pfad und den Interpreter.

**`#req` Reference-Semantik (CSSC v6 — ref by default, `&` für Kopie):**
- `#req[X] Y;` — **True Reference** (Default): `Y` liest und schreibt durch zur originalen Slot von `X`. `Y += 1` erhöht echt `X`. Native-Compiler emittiert `cssc_scope_alias()`; Interpreter routet via Pointer-Wrapping. **Das ist die Default-Form** — analog zur Funktions-Arg-Default-Semantik (`f(x)` ist Ref).
- `#req[X] &Y;` — **Snapshot** (expliziter Deep-Copy): `Y` ist ein eingefrorenes Abbild von `X` zum Aufrufzeitpunkt. Schreibzugriffe auf `Y` mutieren `X` **nicht**. Für primitive Typen identisch zu Ref (Wert wird sowieso kopiert); für `string`, `vector`, `map`, `bind`, Objects, Sektoren ein rekursiver Deep-Copy.
- `#req[X] *Y;` — **Deprecated Legacy-Form** für True Reference. Bleibt zur Migration erhalten, gleiche Semantik wie `#req[X] Y;`. Neuer Code: `*` weglassen.

Beide Modi funktionieren in Interpreter UND nativem Build identisch. Bei Default-Ref wird der Slot wirklich geteilt — `#delete[Y]` im Body invalidiert auch das äußere `X` (Cross-Frame-Delete per Spec §2.5).

### 10.4g `gipeo` — GPIO + Embedded-Peripherals

Das Kernmodul für Mikrocontroller-Programmierung — deckt GPIO, I2C, SPI, UART, ADC, PWM und Hardware-Timer ab. Eine `#include('gipeo') gipeo;` Zeile gated alle 7 Direktiven. Designed für **ESP32-S3, Raspberry Pi 5 und Arduino** (AVR & ARM).

```cssc
#include('gipeo') gipeo;

// 1. Single GPIO pin
#pin[5] led;
led.mode(gipeo::OUTPUT);
led.send(gipeo::HIGH);
#stack[int, 8] s = led.status();

// 2. I2C (BME280 sensor on ESP32 default pins)
#i2c[0, 21, 22] bus;            // bus, SDA, SCL
bus.begin(400000);              // 400 kHz fast mode
bus.write(0x76, [0xF4, 0x27]);  // ctrl_meas register
#stack[array<int>, 256] data = bus.read(0x76, 0xFA, 3);

// 3. SPI
#spi[0, 18, 19, 23] sbus;       // bus, SCK, MISO, MOSI
sbus.begin(1000000, 0);         // 1 MHz, mode 0
#stack[array<int>, 32] resp = sbus.transfer([0x9F]);

// 4. UART
#uart[1, 17, 16] u;             // bus, TX, RX
u.begin(115200);
u.println('hello uart');

// 5. ADC (analog read)
#adc[34] battery;
battery.configure(12, 3300);    // 12 bits, 3.3V vref
#stack[int, 16] mv = battery.read_mv();

// 6. PWM (LED dimming, motor control)
#pwm[18, 5000, 8] motor;        // pin, freq Hz, resolution bits
motor.duty_pct(75.0);

// 7. Hardware timer
#stack[int, 32] ticks = 0;
#define(on_tick) {
    #req[ticks] t;     // v6 Default-Ref (legacy `*t` deprecated)
    t += 1;
}
#timer[0, 1000] heartbeat;      // slot, Hz
heartbeat.attach(on_tick);
heartbeat.start();
```

**Direktiven-Tabelle:**

| Direktive | Bedeutung | Methoden |
|-----------|-----------|----------|
| `#pin[N] var;` | GPIO-Line, Pin N | `.mode(m)`, `.send(level)`, `.status()`, `.toggle()`, `.attach_interrupt(cb, edge)`, `.detach_interrupt()`, `.num()` |
| `#i2c[bus, sda, scl] var;` | I2C-Master | `.begin(freq)`, `.write(addr, data)`, `.read(addr, reg, n)`, `.scan()` |
| `#spi[bus, sck, miso, mosi] var;` | SPI-Master | `.begin(freq, mode)`, `.transfer(data)`, `.transfer_byte(b)` |
| `#uart[bus, tx, rx] var;` | UART/Serial | `.begin(baud)`, `.write(data)`, `.println(line)`, `.available()`, `.read_line()` |
| `#adc[pin] var;` | ADC analog input | `.configure(bits, vref_mv)`, `.read_raw()`, `.read_mv()` |
| `#pwm[pin, freq, bits] var;` | PWM output | `.duty(raw)`, `.duty_pct(pct)`, `.stop()` |
| `#timer[slot, hz] var;` | Periodic timer | `.attach(callback)`, `.start()`, `.stop()` |

**Konstanten im `gipeo::`-Namespace:**
- Direction: `INPUT`, `OUTPUT`, `INPUT_PULLUP`, `INPUT_PULLDOWN`, `OPEN_DRAIN`
- Level: `LOW` (0), `HIGH` (1)
- Edge: `RISING`, `FALLING`, `CHANGE`
- Helpers: `gipeo::delay_ms(ms)`, `gipeo::millis()`, `gipeo::micros()`

**Native Target Mapping** (kompiliere mit dem passenden `--<chip>`-Flag, siehe 10.5b):

| Directive | ESP32-S3 (ESP-IDF) | Arduino (AVR/ARM) | Raspberry (Linux) |
|-----------|---------------------|-------------------|-------------------|
| `#pin`    | `gpio_set_level` / `gpio_get_level` | `digitalWrite` / `digitalRead` | libgpiod |
| `#i2c`    | `i2c_master_*` | `Wire` lib | `/dev/i2c-N` (ioctl) |
| `#spi`    | `spi_device_transmit` | `SPI` lib | `/dev/spidev*` |
| `#uart`   | `uart_write_bytes` | `Serial` | `/dev/ttyAMA*`, `/dev/ttyS*` |
| `#adc`    | `adc_oneshot_*` | `analogRead` | extern (Pi hat keinen nativen ADC; MCP3008 etc.) |
| `#pwm`    | `ledc_*` | `analogWrite` / Tone | `/sys/class/pwm/*` |
| `#timer`  | `gptimer_*` | `Timer1`/`Timer2` libs | `timerfd_create` |

**Host-Interpreter-Modus** (Tests ohne Hardware): jede Direktive instanziiert ein Stub-Objekt das alle Reads/Writes auf stderr loggt (`[gipeo] pin[5].send(HIGH)`). I2C round-trippt Schreib-Werte (Write 0xF4→[reg, val] / Read denselben reg gibt val zurück) — das reicht um Sensor-Treiber-Logik offline zu testen, bevor die Hardware angeschlossen wird.

### 10.4h `allocwatcher` — Live Allocation-Visualizer

Ein natives GUI-Fenster, das die Allokations-Stores des Runtimes (stack/heap/auto) in Echtzeit spiegelt: gesamter Bit-Verbrauch, per-Allokation Lifetimes, Event-Log. Threaded, blockiert das Host-Script nicht. Unter `--no-console` oder ohne Tk fällt's auf periodische stderr-Snapshots zurück.

```cssc
#include('allocwatcher') aw;

aw::watch();                              // watch das ganze Runtime

#stack[int, 32] x = 5;
#heap[vector<int>, 4096] data = [];
// … weiter Code mit Allokationen …

aw::snapshot() snap;                      // assertbar in Tests
cssc::outln('live=' + snap['live_count']);

aw::stop();                               // schließt GUI + final summary
```

**Funktionen:**
| Funktion | Bedeutung |
|----------|-----------|
| `aw::watch(target?)` | Visualizer öffnen. Optionales `target` = sector/object, dessen Allokationen gefiltert werden. Ohne Arg: ganzes Runtime. Ersetzt einen evtl. laufenden Watcher. |
| `aw::stop()` | GUI schließen, Final-Summary auf stderr (`X alloc / Y free / Z lifecycles`). |
| `aw::snapshot()` | Dict zurückgeben: `{live_count, total_bits, allocs, frees, elapsed_s, active}` — perfekt für Assertions in Tests, ohne GUI öffnen zu müssen. |

**Was im Fenster angezeigt wird:**
1. Statuszeile — `target | t+Xs | live=N | bits=B (KiB) | allocs=A | frees=F`
2. Live-Tabelle — jede `#stack`/`#heap`/`#auto`-Variable mit Type, Bits, und Age in Sekunden
3. Recent Lifecycles — letzte 30 zerstörte Allokationen mit Lifetime

**Filter auf einen Sektor**:

```cssc
sector __main__ {
    #stack[int, 32] x = 5;
    #heap[vector<int>, 1024] items = [];
}
aw::watch(__main__);   // tracked nur Allokationen innerhalb __main__
```

**Polling-Cadence:** 100ms (10 Hz Refresh). Auf Embedded-Targets (`cssc build --esp32 / --arduino / --raspberry`) wird das GUI durch eine UART-formatierte Status-Tabelle bei 1Hz ersetzt — gleiche Daten, keine Tk-Dependency.

### 10.4k `video.sprite` — Sprites, Sprite-Sheets, Animationen

Auf dem `video`-Modul aufsetzendes Sprite-System. Kein pygame, kein PIL — 24/32-bit BMP direkt via `struct` geladen, alle Blits über `ctypes.memmove` in den Framebuffer.

```cssc
#include("video") vid;
#include("video.sprite") sprite;

#video[320, 240, 60] w;
video::open(w, "Sprites Demo");

var hero = sprite::loadBmp("hero.bmp", 0xFFFF00FF);
video::clear(w, 0xFF102030);
sprite::draw(hero, w, 100, 80);
sprite::drawTinted(hero, w, 140, 80, 0xFFFF3040);
sprite::drawScaled(hero, w, 180, 80, 32, 48);
video::present(w);
```

**Kern-API** (`sprite::`):

| Methode | Signatur | Wirkung |
|---------|----------|---------|
| `create(w, h [, keyArgb])` | → `Sprite` | Leerer Sprite mit optionaler Color-Key-Transparenz |
| `createFromAscii(rows, palette)` | → `Sprite` | ASCII-Art-Sprite: `'.'` ist transparent, andere Zeichen → Palette-Farbe |
| `loadBmp(path [, keyArgb])` | → `Sprite` | 24- oder 32-bit BMP laden (bottom-up + top-down) |
| `setPixel / getPixel / setKey / clear` | | Direkter Pixel-Zugriff |
| `draw(spr, target, x, y)` | | Opake Blit mit Color-Key |
| `drawScaled(spr, target, x, y, outW, outH)` | | Nearest-Neighbor-Scaling |
| `drawTinted(spr, target, x, y, tintArgb)` | | Per-Channel-Multiply-Tint |
| `drawAlpha(spr, target, x, y, alpha)` | | Alpha-Blending (0-255) |
| `drawFlipped(spr, target, x, y, flipX, flipY)` | | Horizontal/vertikal spiegeln |

**Sprite-Sheets** (`sprite::sheet*`):

| Methode | Beschreibung |
|---------|--------------|
| `sheetCreate(w, h, tileW, tileH)` | Leeres Sheet mit Grid-Layout |
| `sheetLoadBmp(path, tileW, tileH)` | BMP als Sheet laden, auto-slice |
| `sheetFrame(sheet, index)` | Sprite-View auf Einzelframe (Kopie) |
| `sheetDrawFrame(sheet, target, x, y, index)` | Direkt-Blit ohne Kopie |
| `sheetCols / sheetRows` | Grid-Dimensionen |

**Animationen** (`sprite::anim*`):

```cssc
var walk = sprite::animCreate(sheet, [0, 1, 2, 1], 12.0, true);
loop:
    sprite::animUpdate(walk, 16);           // dt in ms
    sprite::animDraw(walk, w, playerX, playerY);
    if (sprite::animFinished(walk)) sprite::animReset(walk);
```

**Collision** (`sprite::hit*`):

| Methode | Zweck |
|---------|-------|
| `hitAabb(ax, ay, aw, ah, bx, by, bw, bh)` | AABB × AABB |
| `hitPoint(px, py, x, y, w, h)` | Point-in-Rect |

Alle Blits klippen automatisch am Framebuffer-Rand. `keyArgb` bezeichnet die pixelgenaue Color-Key-Transparenz (typisch `0xFFFF00FF` "magenta"). BMP-Loader unterstützt 24-bit (opak) und 32-bit (mit Alpha).

### 10.4l `video.tilemap` — Tilemaps + Camera + Kollision

Grid-basiertes Tilemap-Rendering für 2D-Levels. Nutzt `video.sprite`s `SpriteSheet` als Tileset, führt Solid-Tile-Flags für AABB-Kollision, hat Camera mit Follow + Clamp-Bounds.

```cssc
#include("video") vid;
#include("video.sprite") sprite;
#include("video.tilemap") tm;

#video[320, 240, 60] w;
video::open(w, "Tilemap");

var tileset = tm::tilesetLoadBmp("tiles.bmp", 16, 16, 0xFFFF00FF);
var map = tm::create(tileset, 40, 30);              // 40×30 tiles = 640×480 world
tm::setLayout(map, [0, 0, 1, 1, 2, ...]);           // 1200 tile IDs
tm::setSolid(map, 1, true);                          // tile 1 = wall
tm::setSolid(map, 4, true);                          // tile 4 = spikes

var cam = tm::cameraCreate();
tm::cameraSetBounds(cam, 0, 0, 640, 480);

loop:
    tm::cameraFollow(cam, playerX, playerY, 320, 240);
    if (!tm::collideAabb(map, playerX + dx, playerY, 12, 16)) {
        playerX += dx;
    }
    video::clear(w, 0xFF000000);
    tm::draw(map, w, cam);
    video::present(w);
```

**Tileset** (`tm::tileset*`): SpriteSheet-Loader; identisch zu `sprite::sheetLoadBmp`, nur semantisch klarer.

**Tilemap** (`tm::create / setTile / getTile / fill / setLayout`): Grid aus `int32`-Tile-IDs. `-1` = leere Zelle (nicht gerendert).

| Methode | Zweck |
|---------|-------|
| `create(tileset, cols, rows)` | Neue Tilemap |
| `setTile(map, col, row, tileIdx)` / `getTile(map, col, row)` | Zellzugriff |
| `fill(map, tileIdx)` | Alle Zellen setzen |
| `setLayout(map, tileArray)` | Bulk-Load aus Array (row-major) |
| `width / height / tileWidth / tileHeight / pixelWidth / pixelHeight` | Dimensionen |
| `setSolid(map, tileIdx, solid)` / `isSolid` | Solid-Flag pro Tile-ID |
| `draw(map, target, cameraOrX, y)` | Blit mit Camera oder Offset |
| `collideAabb(map, x, y, w, h)` | AABB-Query gegen alle Solid-Zellen |
| `tileAtWorld(map, worldX, worldY)` | Zellinhalt an Weltkoordinate |

**Camera** (`tm::camera*`): Weltkoordinaten → Screen-Koordinaten, mit optionalen Bounds-Clamps für Level-Ränder.

| Methode | Zweck |
|---------|-------|
| `cameraCreate([x, y])` | Neue Camera |
| `cameraSet / cameraMove` | Position setzen/verschieben |
| `cameraFollow(cam, targetX, targetY, viewW, viewH)` | Zentrieren + Bounds-Clamp |
| `cameraSetBounds(cam, x, y, w, h)` | Verschiebungs-Clamps |
| `cameraX / cameraY` | Aktuelle Position |
| `worldToScreen / screenToWorld` | Koordinaten-Transform |

**Perf-Charakteristik:** `tm::draw` blittet nur die im View sichtbaren Tiles (Cull am Camera-Rand); ein 40×30-Level mit 320×240 View kostet ~20×15 Blits pro Frame, bei 16×16-Tiles ~4800 pixels — deutlich unter 1 ms auf Modern-x86.

### 10.4m `video.font` — Bitmap-Fonts + Text-Metriken

Text-Rendering für HUDs, Score, Dialog-Boxes. Bundelt eine 5×7-ASCII-Font (dieselbe wie `video::drawText`) und lädt Grid-Fonts aus BMP.

```cssc
#include("video") vid;
#include("video.font") font;

#video[320, 240, 60] w;
video::open(w, "Font Demo");

var f = font::builtin();
font::setScale(f, 2);
font::draw(f, w, 10, 10, "Score: 12345", 0xFFFFEE00);

var big = font::loadBmp("bigfont.bmp", 16, 24, 32);   // 16×24 glyphs, ASCII 32+
font::draw(big, w, 10, 40, "GAME OVER", 0xFFFF3040);
font::drawWrapped(big, w, 10, 80, "Long message that gets wrapped at the given max width...", 0xFFFFFFFF, 300);

video::present(w);
```

**API** (`font::`):

| Methode | Zweck |
|---------|-------|
| `builtin()` | Bundled 5×7 ASCII-Font (immer verfügbar, keine Datei nötig) |
| `loadBmp(path, glyphW, glyphH [, firstChar=32])` | Fixed-Grid-BMP-Font laden |
| `setKerning(font, pixels)` / `setLineGap` / `setScale` | Tuning (Scale ist Ganzzahl, pixel-perfect) |
| `draw / drawColored / drawScaled` | Text zeichnen |
| `drawWrapped(font, target, x, y, text, argb, maxWidth)` | Wort-Umbruch |
| `measureWidth(font, text)` / `measureHeight` / `lineHeight` | Metriken für Layout |
| `glyphWidth / glyphHeight` | Unskalierte Zellgröße |

Newlines in Text (`\n`) werden respektiert. Der Bundled-Font hat ~95 druckbare ASCII-Glyphen; BMP-Fonts erweitern das auf beliebige Character-Ranges.

### 10.4n Spieleentwicklung mit den video-Modulen — Skelett

```cssc
#include("video") vid;
#include("video.sprite") sprite;
#include("video.tilemap") tm;
#include("video.font") font;
#include("keyboard") kb;
#include("mouse") mouse;

#video[320, 240, 60] w;
video::open(w, "My Game");

var tileset = tm::tilesetLoadBmp("tiles.bmp", 16, 16, 0xFFFF00FF);
var world = tm::create(tileset, 60, 30);
tm::setSolid(world, 1, true);

var sheet = sprite::sheetLoadBmp("hero.bmp", 24, 32, 0xFFFF00FF);
var idle = sprite::animCreate(sheet, [0, 1, 2, 1], 6.0, true);
var run  = sprite::animCreate(sheet, [4, 5, 6, 7], 12.0, true);

var cam = tm::cameraCreate();
tm::cameraSetBounds(cam, 0, 0, 60 * 16, 30 * 16);

var f = font::builtin();
font::setScale(f, 2);

#stack[float, 32] playerX = 100.0;
#stack[float, 32] playerY = 100.0;
#stack[int, 32] score = 0;

loop:
    kb::update();
    mouse::update();
    #stack[float, 32] dx = 0.0;
    if (kb::isPressed("left"))  dx = -2.0;
    if (kb::isPressed("right")) dx =  2.0;
    if (!tm::collideAabb(world, (int)(playerX + dx), (int)playerY, 12, 24)) {
        playerX += dx;
    }
    var animPtr = dx == 0.0 ? idle : run;
    sprite::animUpdate(animPtr, 16);

    tm::cameraFollow(cam, playerX, playerY, 320, 240);

    video::clear(w, 0xFF102030);
    tm::draw(world, w, cam);
    sprite::animDraw(animPtr, w,
                       (int)(playerX - tm::cameraX(cam)),
                       (int)(playerY - tm::cameraY(cam)));
    font::draw(f, w, 4, 4, cssc::str(score), 0xFFFFFFFF);
    video::present(w);
```

### 10.5 `cssc convert` — Transpiler zu Lua/Luau

```powershell
cssc convert script.cssc --luau                  # → script.lua (mit Runtime-Prelude)
cssc convert script.cssc --luau --tiny           # minimal, kein Prelude
cssc convert script.cssc --luau -o out.lua
cssc convert script.cssc --luau -v               # verbose
```

#### `--tiny` (minimal output)

Standardmäßig prependet der Transpiler einen ~120-Zeilen `_cssc`-Runtime-
Prelude (Helpers wie `_cssc.add`, `_cssc.outln`, `_cssc.idx`, …). Mit
`--tiny` bekommst du **direkt** die Ziel-Lua-API:

| CSSC | normal | `--tiny` |
|------|--------|----------|
| `cssc::outln(x)` | `_cssc.outln(x)` | `print(x)` |
| `cssc::out(x)` | `_cssc.out(x)` | `io.write(tostring(x))` |
| `cssc::abs(x)` | `_cssc.abs(x)` | `math.abs(x)` |
| `cssc::len(x)` | `_cssc.len(x)` | `#x` |
| `arr[i]` | `_cssc.idx(arr, i)` | `arr[i+1]` (Literal +1 inline) |
| `s + t` (Strings) | `_cssc.add(s, t)` | `s .. tostring(t)` |
| `n + m` (Numerisch) | `_cssc.add(n, m)` | `n + m` |
| `#delete[x]`, `#free[x]` | als Kommentar | weggelassen (GC managed) |
| `-- sector X`, `-- #include` | als Kommentar | weggelassen |

Konkretes Vorher/Nachher (gleicher CSSC-Quelltext):

```lua
-- normal: 154 Zeilen, 130+ davon Prelude
local _cssc = {}
function _cssc.add(a, b) … end
function _cssc.outln(...) … end
… 120 Zeilen Helpers …
-- #include("retrogadgets") gdt
local counter = 0
while ((counter) < (3)) do
    _cssc.outln(_cssc.add("counter: ", counter))
    counter = _cssc.add(counter, 1)
end

-- --tiny: 13 Zeilen, fertig zum Drop-In
local counter = 0
while ((counter) < (3)) do
    print(("counter: ") .. tostring(counter))
    counter = (counter) + (1)
end
```

**Wann benutzen?**
- **Normal**: für Skripte mit dynamischen `+`-Operationen (Strings + Numerics
  gemischt) oder wenn du den Prelude bewusst möchtest.
- **`--tiny`**: für Retro Gadgets / andere Lua-Hosts wo jeder Speicher-Byte
  zählt, oder wenn du die Lua-Datei manuell weiterbearbeiten willst.

**Achtung mit `--tiny`:** `+` defaulted auf numerisches `+`. Wenn du absichtlich
String-Concat mit unbekanntem Typ machst, schreib's explizit:
```cssc
cssc::outln(cssc::to_string(value) + " ms");   // tostring() forciert String-Concat
```

Transpiliert eine `.cssc`-Datei in einen einzelnen Luau-Script (Lua 5.1+
kompatibel). Das Output enthält:

- Einen Runtime-Prelude mit den von CSSC genutzten Helpers (`_cssc.add`,
  `_cssc.outln`, `_cssc.idx`, `_cssc.len`, `_cssc.range`, …)
- Sektoren als `do … end`-Blöcke + Modul-Tables
- Objects als Lua-Klassen via Metatables (`Foo.new(...)`, `inst:method(...)`)
- Object-Labels als Methoden auf der Klassen-Table
- `#define` als `local function`
- Alle CSSC-Operatoren, Control-Flow, Container-Literale 1:1 übersetzt
- `mirror x` / `return x` → `return x`
- `cssc::*`-Builtins → Lua-Stdlib-Mappings (math.*, table.*, os.*, print, io.*)

**Was nicht übersetzbar ist** wird mit einem Kommentar markiert
(z. B. `#video`, `#thread`, `method`-Bindings, `#redefine`) — manueller
Port nötig.

### 10.5b `cssc build --<chip>` — Embedded Cross-Compile

Native-Builds für **ESP8266 (NodeMCU/Wemos D1/Ideaspark), ESP32-S3, Raspberry Pi (4/5/Zero 2W) und Arduino** (AVR-basierte Boards) werden direkt vom `cssc build` Frontend unterstützt. Vier mutuell exklusive Flags:

```powershell
cssc build script.cssc -o firmware --esp8266      # → firmware.elf + firmware.bin (Xtensa LX106)
cssc build script.cssc -o firmware --esp32        # → firmware.elf (Xtensa LX6/LX7 oder RISC-V)
cssc build script.cssc -o sketch   --arduino      # → sketch.elf  (atmega328p default)
cssc build script.cssc -o pi-app   --raspberry    # → pi-app      (Linux ARM64 ELF)
```

**Toolchain-Mapping (v6-native, kein gcc-Frontend, kein PlatformIO):**

| Flag       | Pipeline                                                                                 | Output |
|------------|------------------------------------------------------------------------------------------|--------|
| (host)     | `cir_lower → cir_to_llvm → llc → lld-link/ld.lld`                                        | `.exe` / nativ |
| `--esp8266`| `cir_lower → transembly/xtensa_lx106.py → xtensa-lx106-elf-as → xtensa-lx106-elf-ld → esptool .bin wrap` | `.elf` + flashable `.bin` |
| `--esp32`  | `cir_lower → transembly/xtensa_lx106.py (LX7 Profile) → xtensa-esp32-elf-as / -ld → esptool .bin wrap` | `.elf` + `.bin` |
| `--arduino`| `cir_lower → cir_to_llvm (avr-unknown-unknown) → llc (--mcpu=atmega328p) → ld.lld -T avr.ld → optional llvm-objcopy .hex` | `.elf` + optional `.hex` |
| `--raspberry`| `cir_lower → cir_to_llvm → llc (aarch64) → ld.lld`                                     | (no ext) |

Externe Abhängigkeiten:

* **Host:** LLVM ≥ 17 (`llc` + `lld-link.exe` / `ld.lld`). `winget install LLVM.LLVM` (Windows), `brew install llvm` (macOS), `apt install llvm` (Linux). Kein gcc, kein cl.exe, kein MSYS2 mehr nötig.
* **Xtensa (ESP8266 / ESP32):** Das hand-getunte Transembly-Backend erzeugt direkt Xtensa-Assembly; der GAS-Assembler aus dem `toolchain-xtensa` PlatformIO-Paket macht daraus `.o`-Dateien, `xtensa-*-elf-ld` linkt. Wenn `xtensa-*-elf-as` nicht auf PATH liegt, installiert der Driver es einmalig per `pip install platformio && pio platform install espressif8266/espressif32` — danach wird PlatformIO selbst nicht mehr aufgerufen, nur die mitgelieferten Tools.
* **`cssc_softfloat.c`** (`includecpp/core/cssl/native/transembly/cssc_softfloat.c`) wird parallel mit `xtensa-*-elf-gcc -O2 -c -ffreestanding -fno-builtin -mlongcalls` übersetzt — die einzige verbleibende C-TU im embedded path. Sie deckt die Softfloat- und Softint-Divide-Thunks ab, die im PlatformIO-`libgcc.a` fehlen (`__divsi3`, `__divdf3`, `__muldf3`, `__floatsidf`, `__fixdfsi`, `__extendsfdf2`, `__truncdfsf2`, `__udivsi3`, `__muldi3`, …). Der User schreibt keine C-Datei selbst.

Dead-Code-Stripping läuft via `--gc-sections` im Linker-Aufruf für alle Embedded-Targets — kein Runtime-Symbol landet im Binary, wenn das User-Module es nicht referenziert. Das ist **per-Feature-TU-Compilation auf Symbol-Level** statt File-Level: ein Skript ohne `#http` zieht die HTTP-Symbole nicht ein, eines ohne `#tft` nicht die OLED-Init-Tabelle, etc.

**Was funktioniert auf welchem Target:**

| Feature | Host-Native (.exe) | ESP8266 | ESP32 | Arduino | Raspberry |
|---------|-------------------|---------|-------|---------|-----------|
| `cssc::outln`, `cssc::out` | ✅ stdout | ✅ UART | ✅ UART | ✅ Serial | ✅ stdout |
| `#stack`, `#heap`, `#delete` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `#define`, `#cdefine`, `#req` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `#daemon`, `#killdaemon` | ✅ pthread | ⚠️ poll | ✅ FreeRTOS | ⚠️ poll | ✅ pthread |
| `#pin/#i2c/#spi/#uart/#adc/#pwm/#timer` (gipeo) | 🔵 stub log | ✅ Arduino-core | ✅ ESP-IDF | ✅ Arduino-core | ✅ libgpiod |
| `#tft`, `#oled` (SSD1306 etc.) | 🔵 stub log | ✅ I²C Wire | ✅ esp_lcd | ⚠️ über lib | ⚠️ fbdev |
| `#video`, `#framebuffer` | ✅ Win32/X11 | ❌ | ❌ | ❌ | ⚠️ headless only |
| `#console[…]` | ✅ AllocConsole / Toplevel | ❌ | ❌ | ❌ | ⚠️ Term-only |
| `cssc::wifi_connect` / `cssc::ntp_sync` | 🔵 no-op-success | ✅ ESP8266WiFi | ✅ esp_wifi | ❌ | ❌ |
| `openai`-Modul | ✅ winhttp/openai-SDK | ❌ | ❌ | ❌ | ✅ libcurl |
| `#raii 0xNN` Hex-Scopes | ✅ | ✅ | ✅ | ✅ | ✅ |

`❌` heißt: das Modul ist auf der Plattform nicht sinnvoll/verfügbar — der Compiler gibt eine klare Fehlermeldung statt Linker-Errors. `⚠️` heißt: bedingt verfügbar, je nach Konfiguration. `🔵` heißt: das Modul loggt seine Calls auf stderr aber führt sie nicht aus (Test-Stub).

**ESP8266/ESP32 → flashable Binary in einem Aufruf:**

```powershell
cssc build script.cssc -o firmware --esp8266 --flash --port COM3
```

Mit `--flash` läuft direkt nach dem Build noch `esptool.py write_flash` mit dem korrekten Offset (0x0 für ESP8266, 0x10000 für ESP32 Anwendungspartition). `--port` / `--baud` werden an esptool durchgereicht. Build und Flash sind **separate Subprozess-Calls**: wenn der Flash fehlschlägt (z. B. kein Board am Port, falsches Kabel) bleibt das Artifact erhalten und kann mit `cssc flash …` nachträglich übertragen werden — siehe 10.5c.

### 10.5c `cssc flash` — Firmware auf das Board schreiben

```powershell
cssc flash firmware.bin --esp8266 --port COM3
cssc flash firmware     --esp8266                # auto-extends .bin
cssc flash firmware.bin --esp32 --port COM5 --baud 921600
cssc flash sketch.hex   --arduino --port COM6
```

Standalone-Befehl wenn Build und Flash zeitlich/örtlich entkoppelt sind. Routet pro Chip an das passende Tool — `esptool.py` für ESP8266/ESP32, `avrdude` für AVR. Ohne `--no-gui` öffnet sich auf Win32 ein nativer Dialog mit CSSC-Watermark, Live-Log und Abbruch-Button.

**Diagnose bei Flash-Fehlern:** Wenn der Port nicht öffnen lässt (häufigster Fall), gibt CSSC strukturierte Hilfe statt eines pyserial-Tracebacks:

```text
cssc-flash: error  could not open serial port COM3.
  Common causes:
   * USB cable is power-only (charge-only) — no data lines.
     Many cheap USB cables can't speak serial. Try a different cable.
   * Wrong COM port. Open Device Manager -> Ports (COM & LPT)...
   * Device not in flash mode. Press BOOT, tap RESET, release BOOT.
   * Driver missing. ESP8266/ESP32 boards need CP210x or CH340 drivers.
cssc-flash: ok     firmware artifact is at: firmware.bin
cssc-flash: hint   retry with: cssc flash firmware.bin --esp8266 --port COMx
```

### 10.5d `cssc scan` — Hardware-Discovery

Zwei Modi: Port-Erkennung und I²C-Bus-Scan.

**`cssc scan --com`** durchsucht alle seriellen Ports, klassifiziert die USB-Brücke (CH340 / CP210x / FTDI / USB-CDC), pingt ESP-Boards mit `esptool chip-id` und druckt pro Device einen direkt einfügbaren `cssc build`-Aufruf:

```text
$ cssc scan --com
======================================================================
  CSSC port discovery — 1 serial port(s) found
======================================================================
  Port:        COM3
  Description: USB-SERIAL CH340 (COM3)
  Bridge:      CH340
  Likely:      esp8266 (most likely) | arduino-clone | esp32
  Probing:     esptool chip-id (12s timeout) ...
  Detected:    ESP8266EX (MAC cc:50:e3:45:d8:07)
  Suggested:
    cssc build script.cssc -o firmware --esp8266 --flash --port COM3
    cssc scan esp8266 --port COM3   # I2C bus scan
======================================================================
```

**`cssc scan <target> --port COM3`** baut + flashed ein winziges Scanner-Sketch und meldet jedes I²C-Gerät auf jedem gängigen Pin-Pair zurück. Erkennt Standard-Adressen (SSD1306, BME280, MPU6050, INA219, TSL2561, …) automatisch und labelt sie:

```text
------------------------------------------------------------
  I2C scan results — esp8266
------------------------------------------------------------
  Pins: GPIO4/5  (D2/D1)
    (empty)
  Pins: GPIO12/14 (D6/D5)
    [DEVICE] 0x3C (SSD1306 OLED)
------------------------------------------------------------
```

Ein Build-Cache unter `~/.cssc/scan-cache/<target>/` macht den ersten Scan einmal ~30 s teuer, jeden weiteren ~3 s schnell. `--no-flash` re-listened ohne erneuten Build.

### 10.5e' `cssc install --target` — Eigene CSSC-Sourcen → Embedded-`.obj`

> **Status:** Dieser Subbefehl ist aktuell der einzige Pfad im Tooling, der noch über die v5-C-Codegen-Brücke läuft. Die Bundle-Layouts unten (`.c`/`.h` im `target/<chip>/`-Tree) reflektieren den aktuellen Stand; mit Phase 5d (AVR-Backend) wird dieser Pfad auf v6-Native-Assembly-Bundles (`<dep>.<target>.s` + vorassemblierte `<dep>.<target>.o`) umgestellt, ohne CLI-Interface zu ändern.

Eigener Code, der auf dem Chip wiederverwendet werden soll (Display-Treiber, Clock-Engine, Sensor-Wrapper), wird zu einer target-spezifischen Dependency kompiliert. Die `.obj` enthält pre-generated C-Source (legacy) bzw. ab Phase 5d Xtensa-/AVR-Assembly, die beim Main-Script-Build statisch ins Firmware-Image gelinkt wird — **kein Runtime-DLL-Loading**, keinerlei Loader-Overhead auf dem Chip.

```powershell
cssc install clock0.cssc --target esp8266 --name clock0
cssc install cpu0.cssc   --target esp8266 --name cpu0
cssc install sensor.cssc --target esp32   --name dht11
```

**Resultat:** `clock0.esp8266.obj` (≈ 18 KB) im aktuellen Verzeichnis. Der Dateiname kodiert immer `<name>.<target>.obj` — so können verschiedene Chip-Varianten desselben Moduls (`clock0.esp8266.obj` neben `clock0.esp32.obj`) koexistieren.

**Manifest** (`manifest.txt` im Bundle):

```
version=2
project=clock0
kind=embedded-dep
target=esp8266
dep_name=clock0
init_fn=cssc_dep_clock0_init
src_filename=clock0.c
header_filename=clock0.h
source=clock0.cssc
```

**Bundle-Layout:**

```
clock0.esp8266.obj
├── manifest.txt
├── target/esp8266/clock0.c   — pre-generated C, entry: cssc_dep_clock0_init
├── target/esp8266/clock0.h   — extern-"C" prototype
└── source/clock0.cssc        — Original-Source (zur Inspektion)
```

**Verwendung im Main-Script:**

```cssc
#depend['core/clock/clock0.esp8266.obj'] Clock;
#depend['core/cpu/cpu0.esp8266.obj']    CPU;

Clock::CPUClock() Firmware->clock;          // object-zugriff via sector
CPU::__CPU__(Firmware->clock) Firmware->cpu;
```

**Build-Pipeline** beim `cssc build firmware.cssc --esp8266`:

1. Pre-scan findet alle `#depend['*.<target>.obj']`-Direktiven.
2. Manifest jeder `.obj` wird verifiziert (`target` muss matchen, sonst Compile-Error mit präzisem Hinweis).
3. `target/<chip>/*.c` wird in PIO `src/` extrahiert, `*.h` nach `include/`.
4. Codegen emittiert `#include "<name>.h"` + `cssc_dep_<name>_init(_scope)`-Aufrufe statt eines dlopen.
5. PIO linkt alles statisch — die deps werden Teil des `firmware.elf`.

**Ownership-Vertrag:** Die `_init`-Funktion liefert eine `CsscVal`-Sektor mit Refcount=1; das Main-Script speichert sie via `cssc_scope_set` (Retain → 2) gefolgt von `cssc_release` des Temps (→ 1). Beim Skript-Ende cascadet `cssc_release_internal` auf den `CSSC_TYPE_SECTOR`: `cssc_sector_free` läuft alle Member ab; ist ein Member ein `CSSC_TYPE_OBJECT`, fährt dessen `free { ... }`-Block automatisch — Reihenfolge: Member-Destruktoren laufen rückwärts, dann die Sektor-Struktur selbst.

**Strikte Constraints im Dep-Source:**

* **Keine Top-Level `#free[X];`-Statements** — der Host besitzt den Lifecycle. Verstöße werden vom Installer mit Zeilennummer+Argument aufgezählt und der Install abgebrochen.
* Dep-Name muss ein gültiger C-Identifier sein (`[A-Za-z_][A-Za-z0-9_]*`) — er wird Teil des `cssc_dep_<name>_init`-Symbols.
* Constructor-Parameter eines `object` im Dep leben **nur im Constructor-Frame**, nicht als Member. Nach `call <label>` aus dem Body sind sie weg — wenn Labels die Werte später brauchen, explizit auf `obj->member` mirroren.

### 10.5e `cssc install --library` — Arduino-Bibliotheken → CSSC `.obj`

Brücke zur kompletten Arduino-Library-Welt: jede Library auf der PlatformIO-Registry (~ 15 000 Projekte) lässt sich in einem Schritt als CSSC-Modul installieren.

```powershell
cssc install --library "Adafruit SSD1306" --esp8266
cssc install --library "DHT sensor library" --esp32
cssc install --library 'adafruit/DHT sensor library' --esp8266    # mit Owner-Prefix
```

**Pipeline:**

1. Auflösung + Download über `pio pkg install --library <NAME> --global` (Cache unter `~/.platformio/lib/<NAME>/`)
2. Rekursiver Scan nach `.h`/`.cpp`/`.c` (skippt `examples/`, `test/`, `docs/`)
3. CSSC-Wrapper-Sektor generiert (für LSP-Autocomplete)
4. Alles in ein ZIP-Bundle packen, abgelegt unter `~/.cssc/libraries/<lib>-<chip>.obj`

**Bundle-Inhalt** (zip-Format, mit `unzip -l` inspizierbar):

```
adafruit_ssd1306-esp8266.obj
├── manifest.json        — name, version, chip, license, author, URL
├── wrapper.cssc         — CSSC-Sektor-Signatur (für Tooling)
├── pio_lib.json         — original PlatformIO library manifest
├── library.properties   — original Arduino IDE manifest
├── README.txt           — human-readable summary
└── src/
    ├── Adafruit_SSD1306.h
    └── Adafruit_SSD1306.cpp
```

Die original Source-Files werden **verbatim** mitgenommen, License-Header bleiben drin — Attribution reist automatisch mit.

**Verwendung in CSSC:** das `.obj` wird via `#require` eingebunden. Auf **Host-Builds** kompiliert `cssc native` das Bundle einmalig zu einem DLL/SO und lädt es über `cssc_obj_load` zur Runtime — gleicher Symbol-Cache, gleicher Sektor-Mirror, anderes Transport-Layer als statische TUs. Auf **Embedded-Targets (ESP8266/ESP32/AVR)** ist `.obj`-Bundling derzeit **nicht** unterstützt: die v6-Native-Pipeline merged keine externen C++-TUs in das Firmware-Binary, weil der Pfad an `cssc_softfloat.c` als einzige eingebettete C-TU gebunden ist und Arduino-Library-Code seine eigene Toolchain-Welt (FreeRTOS, Arduino-Core, ESP-IDF) erwartet. Sub für Embedded: Funktionalität direkt in CSSC nachbauen (siehe das `videodriver.cssc`-Beispiel, das den kompletten SSD1306-Treiber ohne Adafruit-Lib implementiert), oder Host-only entwickeln.

```cssc
#require['~/.cssc/libraries/adafruit_ssd1306-esp8266.obj'] gfx;

// gfx::draw_pixel(x, y, color) etc. — der Arduino-Library-C++-Code wird in
// dein Firmware-Binary mitkompiliert.
```

**Name → Alias-Mapping:** Spaces und Sonderzeichen kollabieren zu Underscores, lowercase. `"Adafruit SSD1306"` → `adafruit_ssd1306`. Filename und `#require`-Alias verwenden dieselbe Transformation.

### 10.5f Embedded-Builtins für Zeit, WiFi & Power

Zusätzlich zu den platformübergreifenden Zeit-Builtins (`cssc::time`, `cssc::date`, `cssc::datetime`, `cssc::detime`, `cssc::sdetime`) gibt es eine Reihe **explizit embedded-bewusste** Helper:

| Builtin | Rückgabe | Verfügbarkeit |
|---------|----------|---------------|
| `cssc::uptime()` | Monotone Sekunden seit Boot (float) | Immer live, RTC-frei |
| `cssc::wifi_connect(ssid, pass)` | bool — true wenn STA-Join erfolgreich (≤ 20 s) | ESP8266/ESP32 (no-op-success auf Host) |
| `cssc::set_timezone(offset_sec)` | bool — setzt POSIX `TZ` für `localtime()` | Alle Targets |
| `cssc::ntp_sync(server)` | bool — true wenn System-Clock per SNTP synchronisiert (≤ 10 s) | ESP8266/ESP32 (no-op-success auf Host) |
| `cssc::reboot()` | (never returns) — `ESP.restart()` / `exit(0)` | Alle Targets |

**Wichtige Semantik der Wall-Clock-Builtins ohne RTC/NTP-Sync:** Auf ESP8266/ESP32 ohne aktiv synchronisierte Uhr returnen `cssc::time/timestamp/date/datetime/detime/sdetime` **`0x0` (null/int 0)** anstatt Uptime — niemals leaked die uptime durch wall-clock-Calls. Das ist die explizite Trennung: wenn du Sekunden-seit-Boot willst → `cssc::uptime()`. Wenn du Berliner Uhrzeit willst → erst `cssc::wifi_connect` + `cssc::set_timezone(3600)` + `cssc::ntp_sync('pool.ntp.org')` aufrufen, dann liefert `cssc::detime()` z.B. `14.32` für 14:32.

```cssc
#include('gipeo')         gipeo;
#include('tft')           tft;
#include('network.http')  http;

#oled[128, 64, 12, 14, 0x3C] display;
display.begin();

// WiFi + NTP für echte Wallclock
if (cssc::wifi_connect('MySSID', 'MyPass')) {
    cssc::set_timezone(3600);                  // Berlin Winter UTC+1
    cssc::ntp_sync('pool.ntp.org');
}

while (true) {
    display.fill(tft::BLACK);
    display.text(0,  0, cssc::datetime(), tft::WHITE, 1);  // 2026-05-10 14:32:18
    display.text(0, 20, cssc::detime(),   tft::WHITE, 1);  // 14.32
    display.text(0, 40, cssc::uptime(),   tft::WHITE, 1);  // 123.456 (sekunden seit boot)
    display.show();
    cssc::sleep(1000);
}
```

**Strikte No-Op-Vermeidung:** Builtins die auf einer Plattform sinnlos sind (z. B. `cssc::exec` auf bare-metal, `cssc::mkdir` ohne Filesystem) **panicen explizit** statt silent zu return-en. `cssc::sleep(ms)` forwarded auf Embedded zu `delay(ms)` (yielded zum WDT), niemals als No-Op — sonst würde der Soft-WDT in jeder `while(true)`-Schleife zuschlagen.

### 10.5g Embedded-Performance & Footprint

Konkrete Messwerte für ein typisches OLED-Demo-Skript (ESP8266 NodeMCU, 80 KB RAM, 4 MB Flash):

```text
RAM:   37.5%  (30,688 / 81,920 bytes)   ← Stack/Heap-Headroom: 51,232 bytes
Flash: 27.4%  (286,159 / 1,044,464 bytes)
Build: 12.5 s  (clean)  /  ~3 s (incremental, Scan-Cache)
Flash: 18.3 s  (esptool, 115200 baud)
```

**Wo gehen die 30 KB hin** (gemessen mit `xtensa-lx106-elf-nm --size-sort` auf dem gelinkten ELF):

| Bytes | Symbol             | Quelle            |
|-------|--------------------|-------------------|
| 1 704 | `g_ic`             | ESP8266 SDK (phy/MAC) |
| 512   | `wvfState`         | ESP8266 SDK |
| 432   | `dns_table`        | lwIP |
| 364   | `__global_locale`  | newlib |
| 256   | `pmc`              | ESP8266 power-mgmt |
| 256   | `event_TaskQueue`  | Arduino-core RTOS |
| 240   | `arp_table`        | lwIP |
| **= ~28 800 B** | **Arduino-core + lwIP + Wi-Fi MAC Fixkost** | |
| 384   | `g_intern_table`   | **CSSC** (tunable via `-DINTERN_TABLE_SIZE=N`) |
| 256   | `g_cssc_last_error`| **CSSC** |
| 192   | `g_cssc_catch_stack`|**CSSC** |
| ~80   | sonstige CSSC      | **CSSC** |
| **= ~900 B** | **CSSC Runtime Fixkost** | |

→ CSSC selbst kostet **~900 Bytes static RAM**. Die übrigen ~28 KB sind Framework-Fixkost die jedes `int main(){}`-Arduino-Sketch ebenso einlinken würde.

**Vergleich zu MicroPython** auf demselben Chip (offizielle MicroPython 1.21 ESP8266-Firmware):

| Metrik                    | MicroPython 1.21 | **CSSC** | Gewinner |
|---------------------------|------------------|----------|----------|
| Firmware-Größe            | ~616 KB          | **287 KB** | CSSC (−53 %) |
| RAM nach Boot             | ~32 KB used      | **30.7 KB used** | gleich (CSSC −4 %) |
| Heap verfügbar für User-Code | ~16 KB        | **~50 KB** | CSSC (3.1× mehr) |
| OLED-Hello-World Zeilen   | ~25              | **8**      | CSSC |
| Boot bis erste Skript-Zeile | ~2.5 s         | **~250 ms** | CSSC (10× schneller) |
| Pixel-Loop-Benchmark¹     | ~12k px/s        | **~1.4M px/s** | CSSC (~110× schneller) |
| GC-Pausen                 | ja (~10–50 ms)   | **keine** | CSSC |
| Native WiFi/HTTP/I²C      | builtin          | builtin + Auto-Pin-Scan | gleich |
| Cross-Compile zu Host?    | nein             | **`cssc run script.cssc`** | CSSC |

¹ Tight-Loop über `display.pixel(x, y, color)` 10 000 Mal. CSSC kompiliert zu nativem xtensa-Maschinencode; MicroPython interpretiert Bytecode via Switch-Dispatch.

**Warum CSSC schneller ist:**

- **Kompiliert, nicht interpretiert.** CSSC-Source → CIR → handgeschriebenes Xtensa-Assembly → native Maschinencode. MicroPython-Bytecode läuft durch einen Switch-Dispatch-Interpreter bei jeder Operation.
- **Kein GC.** CSSC-Scopes besitzen ihre Werte; `}` deterministisch frees den Frame. Transiente String-Allocations (z. B. `("Uptime: " + value)` in einer Hot-Loop) gehen durch einen **Frame-Arena-Allokator**, der beim Scope-Pop bulk-freed wird — keine Per-Allokation-Tracking-Overhead, keine Mark-Sweep-Pausen, keine Stutter-Spikes auf 50 ms Control-Loops.
- **Compile-time Constant-Resolution.** `tft::WHITE` / `gipeo::OUTPUT` / `cssc::int(5)` werden in der CIR zu Literalen aufgelöst und direkt als Immediate-Operanden im Assembly emittiert. Null Runtime-Sector-Lookups für Modul-Konstanten — etwas was MicroPython strukturell nicht kann, weil die Modul-Form erst zur Import-Zeit feststeht.
- **Per-Feature-TU-Compilation** (siehe 10.5b oben).
- **Embedded-tuned Tabellen-Größen.** `INTERN_TABLE_SIZE=32` (statt 4096 auf Host), `MAX_HEX_VARS=8`, `MAX_DAEMONS=2`, `MAX_COBJ_LOADED=1`. Alle via `-D` flippbar am Pain-Point.

### 10.5h `#oled` / `#tft` — Display-Direktiven mit Auto-Pin-Detection

Sugar-Syntax für I²C-OLED-Panels (typisch SSD1306). Zwei Modi:

```cssc
// Discovery — Auto-Scan über sieben gängige Pin-Paare auf ESP8266,
// sechs auf ESP32, plus Adress-Probe 0x3C/0x3D. Ideal für Prototyping.
#oled[128, 64] display;

// Production — explizite Pins + Adresse, kein Auto-Scan.
#oled[128, 64, 12, 14, 0x3C] display;
```

**Volle Syntax:**

```cssc
#tft[ctrl, w, h]                       display;   // Auto-Pin/Adresse
#tft[ctrl, w, h, sda, scl]             display;   // Explizite Pins
#tft[ctrl, w, h, sda, scl, addr]       display;   // + explizite Adresse
```

`ctrl` ist einer aus `tft::SSD1306`, `tft::SH1106`, `tft::ILI9341`, `tft::ST7735`, `tft::ST7789`, `tft::EPAPER`. `#oled[...]` ist sugar für `#tft[tft::SSD1306, ...]` wenn der erste Arg keine bekannte Controller-Konstante ist.

**Auto-Pin-Scan Probier-Reihenfolge auf ESP8266** (bei `#oled[w, h]` ohne explizite Pins):

```text
GPIO4/5  (D2/D1) SDA/SCL    ← Wemos D1 mini Standard
GPIO5/4  (D1/D2) SDA/SCL    ← flipped variant
GPIO14/12 (D5/D6)           ← einige Ideaspark-Boards
GPIO12/14 (D6/D5)           ← swapped
GPIO0/2  (D3/D4)            ← rare
GPIO2/0  (D4/D3)
GPIO13/15 (D7/D8)           ← HSPI pins
```

Pro Pin-Pair Probe bei 0x3C und 0x3D mit Bus-Warmup + 3× Retry. Findet eines davon einen SSD1306, wird's gebunden + `init OK` an UART geloggt. Findet nichts auf einem Pair: voller Bus-Scan (0x08–0x77) und log aller Responder — nützlich für Hardware-Debugging.

**API** (auf dem zurückgegebenen Display-Wert):

| Methode | Signatur | Beschreibung |
|---------|----------|--------------|
| `.begin()` | — | I²C-Init + SSD1306-Init-Sequenz, framebuffer cleared |
| `.fill(color)` | `int color` | `tft::BLACK` (0) oder `tft::WHITE` (non-zero) — alles |
| `.clear()` | — | Alias für `.fill(tft::BLACK)` |
| `.pixel(x, y, color)` | — | Setzt/löscht ein Pixel im Framebuffer |
| `.line(x0, y0, x1, y1, color)` | — | Bresenham-Linie |
| `.rect(x, y, w, h, color)` | — | Outline-Rechteck |
| `.fillrect(x, y, w, h, color)` | — | Gefülltes Rechteck |
| `.text(x, y, str, color, scale)` | scale 1..8 | 5x7-Font, integriertes ASCII-Glyph-Table |
| `.show()` | — | I²C-Flush des Framebuffers (1024 Bytes / SSD1306 128×64) |
| `.width()` / `.height()` | — | Panel-Dimensionen |
| `.close()` | — | Destroy + scope-cleanup |

Farben (`tft::*`-Konstanten): `BLACK`, `WHITE`, `RED`, `GREEN`, `BLUE`, `CYAN`, `MAGENTA`, `YELLOW` — RGB565 auf Farb-Panels, 1bpp auf SSD1306 (jeder Non-Zero = "on"). Die Konstanten werden **compile-time** zu Integer-Literalen aufgelöst — keine Runtime-Sektor-Lookups.

### 10.5i `cssc diagnostics` — Live-Profiler für Skript & Chip

Zwei Modi, beide enden in einem nativen Tk-Fenster ("CSSC Diagnostic Provider") mit fünf Tabs.

```powershell
# Interpreter-Modus — keine Hardware nötig
cssc diagnostics script.cssc                 # default --listen 45s
cssc diagnostics script.cssc --listen 10

# Chip-Modus — baut mit -DCSSC_DIAG=1, flashed, lauscht auf der Serial
cssc diagnostics firmware.cssc --esp8266 --port COM3
cssc diagnostics firmware.cssc --esp8266 --port COM3 --listen 120
```

**Window-Layout** (alle Tabs scrollbar, monospace):

| Tab | Inhalt |
|---|---|
| **SOURCELOG** | Pro Top-Level-Statement eine Zeile mit `[t]` + `L<n>:` — `[0.000s] L14: #stack[string, 256] localtxt` |
| **CHIPLOG** | Rohstrom vom Serial-Port; jede Zeile mit Zeitstempel. Bei `Find in log` highlighting der Quelle-Zeile in Gelb |
| **MEMORY** | Tabelle aller Variable (`name | kind | count | last | peak`) sortiert nach Peak-Größe. Chip-Snapshots aus `[cssc-mem] heap=N free=N` werden als `__chip_heap__` / `__chip_free__` mitgetracked |
| **CPU** | Funktions/Label-Calls (`function | calls | total ms | max ms | avg ms`) sortiert nach Total-Zeit |
| **GENERAL** | Summary oben + **interaktive Tabelle aller Crashes/Faults** |

**Crash-Tabelle in GENERAL**. Spalten:

| Spalte | Beispiel |
|---|---|
| × count | `× 9` — wie oft derselbe Fault aufgetreten ist |
| first @ (s) | `0.718` — Zeit des ersten Auftretens |
| kind | `Exception (3)`, `rst cause:1`, `wdt reset`, `abort()` |
| cause | `LoadStoreErrorCause — unaligned or out-of-range memory access (often null deref)` |
| epc1 / pc | `0x40100a75` — Program Counter beim Fault |
| excvaddr | `0x4006fd51` — Adresse die zugegriffen wurde |
| #stack | `29` — Anzahl Code-Segment-Frames im Stack-Dump |

Identische Faults werden via `(kind, epc1, excvaddr)`-Schlüssel **dedupliziert** — ein ESP im Reboot-Loop mit denselben 9 Crashes produziert **eine Zeile**, nicht neun.

**Rechtsklick auf eine Zeile** öffnet das Kontextmenü:

| Option | Wirkung |
|---|---|
| **Decode trace…** | Findet `xtensa-lx106-elf-addr2line` aus dem PIO-Toolchain-Cache, läuft gegen die Firmware-`.elf`, resolvet epc1 + jede Stack-Code-Adresse zu Funktionsnamen + Source-Dateien. Beispiel-Output: `0x40100a75 → umm_malloc_core` (Heap-Allokator-Crash) |
| **Find first line in CHIPLOG** | Wechselt automatisch zum CHIPLOG-Tab und highlightet die Original-Dump-Zeile gelb |
| **Copy raw dump** | Kopiert den vollständigen Exception-Block (alle Stack-Zeilen) in die Zwischenablage — direkt einfügbar im Arduino IDE's "ESP Exception Decoder" |

**Save-log** (Header-Button): schreibt alle fünf Tabs + Crash-Tabelle nach `%USERPROFILE%\Documents\CSSC\<YYYY-MM-DD_HHMMSS>-<chip>.log`.

**Chip-Markers** (nur in Diagnostics-Build):

```
[cssc-mem] heap=27384 free=23512
[cssc-cpu] _clock 8.0ms
```

Diese Linien werden vom Listener parsed:
* `[cssc-mem]` → `__chip_heap__` (current free) und `__chip_free__` (min-seit-boot) in MEMORY-Tab. Min-tracking zeigt Fragmentation-Trend.
* `[cssc-cpu]` → Call-Stats in CPU-Tab.

Aus dem Script via Builtins:

```cssc
cssc::diag_enable(1);                          // toggle (default-on im Diag-Build)
cssc::diag_mem();                              // emit one heap snapshot now
cssc::diag_cpu("fast_path", elapsed_ms);       // explicit call-time marker
```

**Production vs. Diagnostics-Build**:

| | `cssc build` (Production) | `cssc diagnostics` (Investigation) |
|---|---|---|
| Compile-Flag | — | `-DCSSC_DIAG=1` |
| `cssc::diag_*` Aufrufe | Empty stubs, ~5 Cycles overhead | Echte Emits über Serial |
| Auto-Tick im `loop()` | Nicht eingebaut | 1Hz `[cssc-mem]` Emit |
| Flash-Footprint | 305 339 B (User-Beispiel) | 305 711 B (+ 372 B / +0.12%) |
| RAM-Footprint | 32 028 B | 32 072 B (+ 44 B / +0.13%) |

Production-Firmware enthält **null Diagnostics-Bloat**. Die `#ifdef CSSC_DIAG`-Gates lassen ESP8266 mit 80 KB RAM Luft zum Atmen.

### 10.5j Was hinter dem CSSC-Backend steckt — die v6 Native-Pipeline

CSSC v6+ besitzt seine eigene Codegen-Pipeline End-zu-End. Kein C-Codegen-Zwischenschritt, kein gcc-Aufruf, kein PlatformIO-Wrapping. `cssc build` und `cssc native` sind Aliase auf diesen Pfad:

```
.cssc source
   │  CsscLexer + CsscParser       (cssl_cssc.py)
   ▼
AST  (Python dicts, v5-Shape)
   │  cir_lower.lower()            (native/cir/cir_lower.py)
   ▼
CIR  (CSSC Intermediate Representation — SSA, refcount-aware)
   │  cir_to_llvm.render()         (native/cir/cir_to_llvm.py)
   ▼
LLVM IR (.ll Text)
   │  llc / clang -c -x ir
   ▼
ELF / PE Objekt
   │  lld-link / ld.lld
   ▼
Native Executable (.exe / .elf)

                ┌─────────────────────────────────────────┐
                │  Transembly runtime emitter             │  ← parallel zum User-IR,
                │  native/transembly/x86_64.py            │     erzeugt cssc_print_*,
                │   ├─ Phase 1: emittiert LLVM-IR         │     cssc_runtime_init/shutdown,
                │   └─ Phase 2+: handgeschriebenes Target-│     refcount-Cascade, …
                │                Assembler + COFF/ELF-    │
                │                Objekt-Emitter           │
                └─────────────────────────────────────────┘
```

**Warum dieser Aufbau?** Drei strukturelle Gewinne gegenüber einem C-Zwischen-Codegen-Pfad:

1. **Keine fremde Compiler-Abhängigkeit im Hot-Pfad**: Nur LLVM (für Host & Pi) bzw. `xtensa-*-elf-as`/`-ld` (für ESP). Kein PlatformIO-Wrapper, kein C-Frontend.
2. **CIR kennt das `CsscVal`-Layout, gcc nicht**: Welche Tags zur Compile-Zeit feststehen, welche Slots monomorph sind, wo die Refcount-Cascade Hot-Path ist — der CIR-Emitter sieht das direkt, ein C-Backend müsste es erst aus dem generierten C rekonstruieren.
3. **Hot-Path Hand-Tuning ist möglich**: Eine `cssc_release_internal`-Cascade aus C kompiliert auf ~30 x86-Instruktionen. Mit CIR-spezifischer Hand-Tunung (Tag-Layout, hot-path Tag-Values) sind ~8–12 erreichbar. Bei einer `select`-Loop auf einem 80 MHz ESP8266 ist das der Unterschied zwischen "smooth" und "WDT-resetting".

#### Die CIR (CSSC Intermediate Representation)

Eine minimale SSA-IR, exakt auf CSSC-Semantik zugeschnitten. Jede Funktion ist eine Liste Basic-Blocks; jeder Block eine Sequenz typisierter Ops; jede Op produziert maximal einen Wert mit eindeutiger SSA-ID. Op-Surface (per Phase):

| Op | Bedeutung | Phase |
|---|---|---|
| `const_int` / `const_float` / `const_bool` / `const_str` | Immediate-Werte | 1 |
| `wrap_int` / `wrap_float` / `wrap_bool` | Baue `CsscVal { tag, data }`-Struct | 2 |
| `slot_alloc(kind, bits)` | Stack-Allokation; mono-Optimierung für int/bool/float | 1 |
| `slot_store(slot, value)` | Speichern + Refcount-Bump für Heap-Typen | 1 |
| `slot_load(slot)` | Laden + Retain | 1 |
| `slot_release(slot)` | Dec-Refcount + Cascade | 2 |
| `scope_push` / `scope_pop` / `scope_bind` | Dynamic Scope Frames | 1 (symbolisch) / 2 (Laufzeit) |
| `bin_op` / `cmp_op` | Arithmetik + Vergleich (typisiert per `operand_type`) | 2 |
| `br` / `br_cond` / `ret` | Kontrollfluss-Terminatoren | 2 |
| `call` | Direkter Aufruf einer Runtime- oder User-Funktion | 1 |
| `cssc_outln` | Dispatch zu `cssc_print_int/float/bool/str/val` | 1 |

Refcount ist **inline auf CIR-Ebene**: jedes `slot_store` eines Heap-`CsscVal` emittiert einen Retain, jedes `slot_release` den passenden Dec+Cascade. Der LLVM-IR-Emitter ist deshalb dumm-direkt: textuelle Transkription, keine eigene Analyse-Phase.

**Monomorphe Slot-Optimierung**: Wenn der Compiler weiß, dass ein Slot nur ints hält (`#stack[int, 32] x = 5`), allokiert er `alloca i64` statt `alloca %CsscVal { tag, data }`. Spart 8 Byte pro Slot, vermeidet das Tag-Lese-Branching im Load/Store-Pfad. Genau die Sorte Win, die gcc nicht erkennen kann, weil er das Tag-Layout nicht versteht.

#### Transembly — die Runtime-Schicht

Transembly ist die einzige Stelle, an der CSSC **nicht** durch LLVM-IR geht. Hier wollen wir rohe Maschinen-Instruktionen, die auf das CsscVal-Layout und das Ziel-ISA hand-getuned sind.

* **Host x86_64** (`native/transembly/x86_64.py`): Transembly emittiert die Runtime weiterhin als LLVM-IR. `cssc_print_int(i64)` ruft `printf("%lld\n", n)` über die Standard-libc (msvcrt auf Windows, libc auf Linux). Pragmatisch — Host braucht das letzte Quentchen Maschinencode-Tuning nicht.
* **ESP8266 / ESP32 (Xtensa LX106 / LX7)** (`native/transembly/xtensa_lx106.py`): die komplette Runtime ist hand-geschriebenes Xtensa-Assembly mit CCOUNT-basiertem Timing, IRAM-only Linker-Layout (V1 ROM-Bootloader-kompatibel), Frame-Arena mit `scope_push`/`scope_pop` pro Label-Methode, FNV-1a Hashmap, bit-bang I²C (`cssc_i2c_write_pair` für SSD1306-Init, `cssc_i2c_write_burst` für Framebuffer-Flush), 5×7-Glyph-Tabelle. Plus `cssc_softfloat.c` für die libgcc-Lücken (`__divsi3`, `__muldf3`, `__divdf3`, `__floatsidf`, `__fixdfsi`, `__extendsfdf2`, `__truncdfsf2`, etc.).
* **AVR (atmega328p)** (`native/transembly/avr.py`): ✅ Phase 5d — `cssc native` emittiert LLVM-IR mit `target triple = "avr-unknown-unknown" --mcpu=atmega328p`, das hand-getunte Runtime-Modul liefert UART0-MMIO-Output (`UDR0` @ 0xC6, busy-wait auf `UCSR0A.UDRE0`), 256-Byte Bump-Arena in `.bss`, Refcount-Cascade auf `cssc_str` (4-Feld-Layout `{i16 refcount, i16 size, i16 cap, ptr data}` — 8 Byte statt 24 Byte für SRAM-Knappheit), 8-Frame `cssc_scope_stack` mit Overflow/Underflow-Panics, manuelle Dezimal-Konvertierung in `cssc_print_int` (keine printf auf bare-metal). Link via `ld.lld -T avr.ld` gegen den mitgelieferten Linker-Script — kein gcc, kein avr-libc, kein PlatformIO. `cssc native --target arduino --emit hex` produziert eine avrdude-flashbare Intel-HEX via `llvm-objcopy`. Display-/I²C-/SPI-Treiber landen in Phase 5d.1; der heutige Pfad deckt UART-Sketches + die `videodriver`-Klasse von Demos.

Per-Feature-TU-Compilation bleibt: Transembly emittiert nur Runtime-Symbole, die das User-Module wirklich referenziert. Eine `hello.cssc` zieht ~200 Byte Code, kein Bloat. Die ESP8266-Firmware für `videodriver.cssc` (Object + I²C-OLED + 120-Sekunden-Animation) landet bei ~13 KB `.bin`.

#### Der `cssc native`-Subcommand

```powershell
cssc native script.cssc -o out                # Host-Build (.exe)
cssc native script.cssc -o out --emit ll      # stoppe bei LLVM-IR (zum Inspizieren)
cssc native script.cssc -o out --emit asm     # stoppe bei .s (llc-Output)
cssc native script.cssc -o out --emit obj     # stoppe bei .o
```

Externe Abhängigkeiten: **nur LLVM ≥ 17**. `winget install LLVM.LLVM` (Windows) / `brew install llvm` (macOS) / `apt install llvm clang` (Linux) installiert `clang` + `lld-link` + `ld.lld`. Kein gcc, kein cl.exe, kein MSYS2.

Negatives Verhalten ist explizit: trifft die Lowering auf einen AST-Knoten, der noch nicht implementiert ist (einzelne weiterführende Module, AVR-Peripheral-Treiber aus Phase 5d.1), bricht der Build mit einer Zeilennummer und der Meldung `<feature> not yet implemented for target <X>` ab. **Kein Silent-Fallback, keine TODO-Stubs.**

#### `cssc native trace` — statischer ABI-/Codegen-Scanner

```powershell
cssc native trace script.cssc                 # default: a0 / cs / align / iram / recursive
cssc native trace script.cssc --mode a0,cs    # nur die zwei Klassen
cssc native trace script.cssc --mode sp       # opt-in: SP-Displacement (laut, oft Noise)
cssc native trace script.cssc --json          # machine-readable
```

Trace baut das Script bis zur `.s`-Stufe und walked das Xtensa-Assembly nach den Bug-Klassen, die uns während des v6-Bring-ups aufgehalten haben:

| Mode (Default-Set) | Was es erkennt |
|---|---|
| `a0` | `call0 X` in einer Funktion, die a0 nie auf den Stack gerettet hat → das spätere `ret.n` springt auf eine korrupte Adresse (typischerweise PC=0x40001800 ROM panic) |
| `cs` | Funktion schreibt eine von a12..a15 ohne sie zu sichern; verletzt CALL0-Callee-Save-ABI |
| `align` | `call0 LABEL` wo `LABEL:` keinen `.align 4` davor hat; Cause-0 IllegalInstruction wenn der Linker es nicht zufällig aligned |
| `iram` | `l8ui` / `s8i` auf einem Pointer, der nach Layout in IRAM zeigt — auf ESP8266 raised das Cause-3 LoadStoreErrorCause |
| `recursive` | Funktion ruft sich selbst ohne a0 zu sichern → garantierte Endlos-Tail-Korruption |

`sp` (SP-Displacement-Spill) ist opt-in, weil seit der Emitter `_sp_displacement` korrekt kompensiert ist, jeder legitime Compensated-Load die alte Heuristik triggert.

#### Phasen-Status

| Phase | Surface | Status |
|---|---|---|
| **1** — Hello-World End-zu-End | `#stack[int, N]`, `cssc::outln(int)`, `#delete` | ✅ done |
| **2** — Full Value Surface | Arithmetik & Vergleich (int + f32 + f64), `if/else`, `while`, `for`, Assignment, unary, logical `&&` / `||`, Strings (`cssc_string_lit`, `cssc_string_concat`, `cssc_float_to_str` mit `[-]INT.FFF`-Decimal-Format) | ✅ done |
| **3** — Container-Surface | `vector<T>`, `array<T>`, `map<K,V>`, `bind`, `[i]`, `select`/`jump` | ✅ done (smoke-tested via `_smoke_xtensa.py` C1/C2) |
| **4** — Sectoren / Objekte / Methoden | `sector`, `object`, Labels (`boot`/`tick`/`free` + custom), `call`/`mirror`/`destruct`, Method-System, `#include`/`#depend`, Ref-Captures `<*display, *tft>`, Object-Arena-Scope-Push/Pop pro Label-Methode | ✅ done |
| **5a** — ESP8266 (Xtensa LX106) | Volles Embedded-Target inkl. handgeschriebene SSD1306 I²C-Init, `cssc_i2c_write_pair`/`_burst`, `cssc_tft_text`/`_fill`/`_pixel`/`_fillrect`/`_show`, CCOUNT-basierte `cssc_uptime`/`cssc_sleep_ms`/`cssc_tick`, IRAM-only V1 ROM-Image-Wrapping, eboot-konforme `.bin` | ✅ done (verified on real hardware) |
| **5b** — ESP32 (Xtensa LX7) | Profile-Substitution in derselben transembly-Pipeline; FPU-Path für f32 BinOps | ✅ profile vorhanden, hardware-bring-up pending |
| **5c** — Raspberry Pi (aarch64-linux) | LLVM-IR-Pfad mit `aarch64-unknown-linux-gnu` triple, `ld.lld` linker | ✅ done |
| **5d** — Arduino (AVR atmega328p) | `transembly/avr.py` LLVM-IR-Runtime + `avr.ld` Linker-Script + `_link_avr` Driver-Branch + `--emit hex` über `llvm-objcopy` + Refcount-Cascade auf 8-Byte `cssc_str` für SRAM-Knappheit | ✅ done (lowering + emit smoke-tested; UART-Pfad funktional, simavr/avrdude validation laufen extern) |
| **5d.1** — AVR-Peripheral-Surface | Pin/I²C (TWI)/SPI/UART-RX/ADC/PWM/Timer + SSD1306-OLED auf AVR | pending — Phase 5d hat den Build-/Link-/Flash-Pfad geliefert, die Treiber-Schicht ist die Folge-Iteration |

`cssc build` und `cssc native` sind ab Phase 4 vollständige Aliase auf den v6-Pfad. Der frühere C-Codegen-/PlatformIO-Pfad ist abgekündigt; sein Code bleibt vorerst als Reference im Repo (`cssc_compiler.py`), wird aber nicht mehr getestet.

### 10.6 `#DEFINE` — Foreign-API-Namespace (nur Transpiler)

```cssc
#DEFINE gdt;
#DEFINE math;
#DEFINE my_lib;
```

`#DEFINE name;` deklariert `name` als **fremden API-Namespace**, dessen
Inhalt von der Lua-Zielumgebung bereitgestellt wird. Jeder Zugriff
`name::Sub::Member` wird beim Transpilieren 1:1 zu `name.Sub.Member` —
ohne dass CSSC ein Modul mit diesem Namen kennt.

```cssc
#DEFINE gdt;

sector __main__ {
    gdt::CPU0::State = 1;                      // → gdt.CPU0.State = 1
    gdt::Display::write("Online");             // → gdt.Display.write("Online")
} free {};
#free[__main__];
```

**Semantik in den anderen Pipelines:**

| Pipeline | Verhalten |
|----------|-----------|
| `cssc run` (Interpreter) | `#DEFINE` ist ein No-Op — der Code würde versagen, sobald `gdt::*` evaluiert wird, weil das Modul nicht existiert. Nur beim Transpilieren sinnvoll. |
| `cssc build` (Native) | Auch No-Op — emittiert einen `/* … */`-Kommentar. |
| `cssc convert --luau` | Das eigentliche Ziel. |

**Abgrenzung zu `#define()`** (Kleinschreibung):

| Direktive | Zweck |
|-----------|-------|
| `#define(funcName) { body }` | Funktions-/Callback-Definition (Code) |
| `#DEFINE name;` | Transpiler-Hint, kein Code-Effekt zur Laufzeit |

**LSP**:
- `#DEFINE` wird syntaktisch als Direktive gehighlightet (purple-keyword).
- Der deklarierte Namespace gilt im Editor als bekannt — `gdt::CPU0::Foo`
  produziert keine "unbekannter Namespace"-Warnung.

### 10.7 `#load` / `#unload`

```cssc
#load["./other.cssc"] myMod;
myMod::someFunction();
#unload[myMod];
```

Laedt eine externe CSSC-Datei als Modul. Alle Funktionen und Variablen landen in dem Modul-Sektor.

> **Backend-Hinweis:** `#load` / `#unload` werden nur vom **Interpreter** (`cssc run`, `cssc exec`) und vom Legacy-`--gcc`-Pfad ausgewertet. Das v6-Native-Backend (`cssc build`, `cssc native`) lehnt diese Direktiven mit einem klaren CIR-Lower-Fehler ab — die Laufzeit-Modulauflösung passt nicht zu einem statisch verlinkten Embedded-Binary. Wenn du den Code auf den Chip willst, inline die Quelldatei stattdessen via `#include('…')` oder schreibe sie als CSSC-Modul (siehe §10.5).

### 10.8 LSP — IDE-Support (VSCode & jeder LSP-Client)

CSSC liefert einen vollwertigen **Language Server** ([includecpp/vscode/cssl/server/](includecpp/vscode/cssl/server/)) mit der dazugehörigen VSCode-Extension ([cssl-2.0.0.vsix](includecpp/vscode/cssl/cssl-2.0.0.vsix)). Der Server spricht das standard Language Server Protocol — funktioniert also auch in Neovim, Helix, Sublime LSP und allen anderen Clients.

#### Installation

```powershell
# VSCode-Extension aus dem .vsix einspielen
code --install-extension includecpp/vscode/cssl/cssl-2.0.0.vsix

# Oder manuell: VSCode → Extensions → "..." → Install from VSIX...
```

Sprachen die der Server kennt: `cssl` (`.cssl`), `cssc` (`.cssc`), `cproject` (`.cproject`), `cssl-mod` (`.cssl-mod`), `cssl-pl` (`.cssl-pl`).

#### Provider-Übersicht

| Provider | Datei | Was es macht |
|----------|-------|-------------|
| **Diagnostics** | [analysis/diagnostic_provider.py](includecpp/vscode/cssl/server/analysis/diagnostic_provider.py) | Real-time Errors + Warnings: unbekannte Direktiven, fehlende `#include`s, `#stack`/`#heap` ohne `#delete`, falsche Module-Aliase, unbekannte Methoden, Memory-Leaks |
| **Completion** | [providers/completion_provider.py](includecpp/vscode/cssl/server/providers/completion_provider.py) | IntelliSense für Module-Namen, Methoden auf typisierten Variablen (z.B. `vec.` → `push_back`, `pop_back`, …), `cssc::`-Builtins, Direktive-Argumente, Snippet-Trigger |
| **Hover** | [providers/hover_provider.py](includecpp/vscode/cssl/server/providers/hover_provider.py) | Rich-Markdown-Docs beim Mouse-Hover: Modul-Doku (z.B. `openai`, `devdebug`, `console`, `stdgrace`, `def`), Direktive-Erklärungen, Built-in-Signaturen, Constraint-Annotations |
| **Definition** | [providers/definition_provider.py](includecpp/vscode/cssl/server/providers/definition_provider.py) | Go-to-Definition für Variablen, Funktionen, Sektoren, Objekte, Labels, Modul-Aliase |
| **Signature Help** | [providers/signature_help_provider.py](includecpp/vscode/cssl/server/providers/signature_help_provider.py) | Parameter-Hints während Funktionsaufrufen — zeigt aktuell aktiven Param fett |
| **Semantic Tokens** | [providers/semantic_tokens_provider.py](includecpp/vscode/cssl/server/providers/semantic_tokens_provider.py) | Symbol-klassen-basiertes Coloring: Direktiven (lila), Typen (teal), Variablen (weiss), Funktionen (blau) |

#### Diagnostics — was geprüft wird

```cssc
// 1. Unbekannte Direktive
#xyz[int, 32] foo;
//↑ "unknown directive '#xyz' — did you mean #stack?"

// 2. Direktive verlangt #include
#fvar(int) callback;
//↑ "#fvar requires #include('def') to be loaded first"

// 3. Memory leak warning
#stack[string, 256] msg = "hi";
// (kein #delete[msg] vor scope exit)
//↑ "Potential memory leak: #stack variable 'msg' has no matching #delete[msg].
//    Disable with warn_mem_leak = false in cssc.cproject."

// 4. Modul ohne Free
#include('os') os;
// (kein #free[os] am Ende)
//↑ "module 'os' has no matching #free[os]. Every #include creates a sector
//    that the host script must explicitly free."

// 5. Unbekannte Methode auf bekanntem Typ
#stack[vector<int>, 1024] v = [];
v.unknownMethod();
//↑ "no method 'unknownMethod' on vector<int>"
```

Jede Warnung kann projektweit per `cssc.cproject` Datei abgeschaltet werden:

```toml
warn_mem_leak    = false
warn_module_free = false
```

#### Module-Whitelist (`_CSSC_BUILTIN_DIRECTIVES`)

Der Server kennt jede built-in Direktive samt Modul-Anforderung. Bei `#scanp_opt`, `#fvar`, `#param`, `#cdefine`, `#qvar`, `#scanp` z.B. wird `#include('def')` verlangt; bei `#debug` / `#trace` `#include('devdebug')`; bei `#catch` `#include('stdgrace')`. Fehlt das Include, gibt's eine Diagnostic mit konkretem Fix-Hint.

#### Hover-Beispiel

```cssc
#include('openai') ai;
ai::OpenAIClient(key) MyAI;
//   ↑↑↑↑↑↑↑↑↑↑↑↑ Hover hier zeigt:
//   "OpenAIClient(api_key, model?, base_url?, timeout?) — primary constructor.
//    Returns: instance with .chat() / .completion() / .set_model() / …"
```

Hover-Provider hat dedizierte Markdown-Docs für: `openai`, `retrogadgets`, `def`, `devdebug`, `stdgrace`, `console`, `cssc.math`, `stdio`, `sizes`, `cssc.peek`, `asyncthreads`, `serialcommunication`, `os`, `keyboard`, `mouse`, `video`, `matrix`, `sound`, `cssc.dll`, `cssc.ini`, `cssc.paths`, `cssc.env`, `cssc.sys`, `cssc.io`, `cssc.fastif`, `cssc.binary`, `cssc.sidepackagetools`. Plus jede Direktive einzeln.

#### Snippets ([cssl.snippets.json](includecpp/vscode/cssl/snippets/cssl.snippets.json))

Tab-Completable Vorlagen — z.B. `def` + Tab → komplettes `#define(<func>) { ... }` Skelett, `cdef` → `#cdefine(<func>, <p1>, <p2>) { ... }`, `obj` → ganze `object Name { ... } free { ... }` Struktur.

#### Syntax Highlighting

TextMate Grammars in [syntaxes/](includecpp/vscode/cssl/syntaxes/):
- `cssc.tmLanguage.json` — `.cssc` Skripte (Direktiven, Typen, Bind-Literale, Hex-Identifier, …)
- `cssl.tmLanguage.json` — `.cssl` (CSSL High-End)
- `cproject.tmLanguage.json` — Project-Konfig

Farbschema folgt durchgehend: **Direktiven lila**, **Typen teal**, **Variablen weiss**, **Funktionen blau** — um Datenfluss vs. Kontrollfluss visuell zu trennen.

#### Manuell starten (für andere LSP-Clients)

```powershell
python -m includecpp.vscode.cssl.server
```

Der Server liest LSP-Messages auf stdin/stdout. Konfiguriere deinen Editor mit:
- Command: `python -m includecpp.vscode.cssl.server`
- File Types: `cssl`, `cssc`, `cproject`, `cssl-mod`, `cssl-pl`
- Root patterns: `cssc.cproject`, `.git/`

#### Was der LSP NICHT macht

- Keine Auto-Formatierung (kein `cssc fmt` Provider — gewollt: bit-genaue Memory-Layouts hat keine "right way" Formatierung)
- Kein Linting für native-Build-spezifische Issues (z.B. `#req` ohne `*` in einem Daemon-Body — wird zur Compile-Zeit bemerkt, nicht im Editor)
- Keine Cross-File-Symbolauflösung über `#include`-Grenzen hinweg jenseits des Modul-Aliases (`#load`-Targets sind nur teilweise erfasst)

---

## 11. Fehlerbehandlung

### 11.1 `#panic`

```cssc
if (value < 0) {
    #panic("Negativer Wert nicht erlaubt");
}
```

Wirft einen kuenstlichen Laufzeitfehler mit Nachricht. Wird auch automatisch bei Constraint-Verstoessen geworfen.

---

## 12. Builtin-Funktionen (`cssc::`)

### I/O

| Funktion | Beschreibung |
|----------|-------------|
| `cssc::out(...)` | Ausgabe ohne Zeilenumbruch |
| `cssc::outln(...)` | Ausgabe mit Zeilenumbruch |
| `cssc::input(prompt)` | Liest eine Zeile von stdin |
| `cssc::sleep(ms)` | Wartet die angegebenen Millisekunden |

### Prozesse

| Funktion | Beschreibung |
|----------|-------------|
| `cssc::run(datei)` | Führt eine `.cssc`-Datei aus und gibt `true`/`false` (Erfolg) zurück |
| `cssc::exec(cmd)` | Führt einen Shell-Befehl aus, gibt stdout als String zurück |

`cssc::run(datei)` startet ein weiteres CSSC-Programm. Der Pfad wird relativ zur
aufrufenden Datei aufgelöst; die Ausgabe des Kind-Programms erscheint inline.
Rückgabe ist ein `bool`: `true` wenn die Datei existiert **und** fehlerfrei
durchläuft, sonst `false` — ein abstürzendes Kind reißt den Aufrufer nicht mit.
Im Interpreter (`cssc run`) läuft das Kind in einem frischen In-Process-Runtime;
im Compiler (`cssc build`) delegiert der Aufruf an den `cssc run`-Interpreter.

```cssc
#stack[bool, 8] ok = cssc::run("setup.cssc");
if (!ok) {
    cssc::outln("setup fehlgeschlagen");
}
```

### Zeit

| Funktion | Beschreibung |
|----------|-------------|
| `cssc::time()` | Aktuelle Zeit als float (Unix-Sekunden) |
| `cssc::timestamp()` | Unix-Zeitstempel als int |
| `cssc::clock()` | Hochpraezise Performance-Counter (float) |
| `cssc::elapsed(start)` | Differenz zu einem `cssc::clock()`-Wert |
| `cssc::date()` | Datum als String `"YYYY-MM-DD"` |
| `cssc::datetime()` | Datum+Zeit als String `"YYYY-MM-DD HH:MM:SS"` |
| `cssc::detime()` | Aktuelle Zeit als float `HH.MM` (z. B. `17.32`) |
| `cssc::sdetime()` | Aktuelle Zeit als float `MM.SS` (z. B. `32.45`) |
| `cssc::time_format(fmt)` | strftime-Formatierung |
| `cssc::uptime()` | Monotone Sekunden seit Boot (float). Auf Embedded RTC-frei, immer live |

> **Embedded-Hinweis:** `cssc::time/timestamp/date/datetime/detime/sdetime` returnen auf Embedded ohne RTC/NTP-Sync **`0x0`** (statt einer gefakten Uhrzeit). Für monotone Zeit-seit-Boot → `cssc::uptime()`. Für echte Wall-Clock → erst `cssc::wifi_connect` + `cssc::set_timezone` + `cssc::ntp_sync` (siehe nächste Tabelle). Detail in 10.5f.

### Netzwerk & System (Embedded)

| Funktion | Beschreibung |
|----------|-------------|
| `cssc::wifi_connect(ssid, pass)` | STA-Join via ESP8266WiFi/esp_wifi. Bool — true wenn ≤ 20 s verbunden |
| `cssc::set_timezone(offset_sec)` | POSIX-`TZ` setzen — z. B. `3600` für Berlin-Winter, `7200` Sommer |
| `cssc::ntp_sync(server)` | SNTP-Sync, danach liefern Wall-Clock-Builtins echte Zeit. ≤ 10 s |
| `cssc::reboot()` | Hard-Reset des Chips (`ESP.restart()`) / `exit(0)` auf Host. Returnt nie |

### Typen

| Funktion | Beschreibung |
|----------|-------------|
| `cssc::typeof(val)` | Gibt den Typnamen zurueck |
| `cssc::to_int(val)` | Konvertiert zu Integer |
| `cssc::to_string(val)` | Konvertiert zu String |
| `cssc::is_string(val)` | Prueft ob String |

### Mathematik

| Funktion | Beschreibung |
|----------|-------------|
| `cssc::abs(x)` | Absolutwert |
| `cssc::min(a, b)` | Minimum |
| `cssc::max(a, b)` | Maximum |
| `cssc::sqrt(x)` | Quadratwurzel |
| `cssc::random()` | Zufallszahl 0.0-1.0 |
| `cssc::random_int(a, b)` | Zufallszahl im Bereich |

### Arrays

| Funktion | Beschreibung |
|----------|-------------|
| `cssc::len(val)` | Laenge |
| `cssc::push(arr, val)` | Element anfuegen |
| `cssc::pop(arr)` | Letztes Element entfernen |
| `cssc::sort(arr)` | Sortieren |
| `cssc::range(start, end)` | Zahlenbereich erzeugen |

---

## 13. Beispiel: Vollstaendiges Programm

> **Hinweis:** Dieses Beispiel demonstriert das **Interpreter-Featureset** (`cssc run`). Es nutzt parametrisierte Method-Templates (`method Bounded<int>`) und Label-Parameter mit Bodies — Konstrukte, die der v6-Native-Build (`cssc build`) noch nicht lowert (Phase 4+ Roadmap). Für ein Embedded-taugliches Vollbeispiel siehe [includecpp/videodriver.cssc](../../videodriver.cssc) — derselbe `object`/`label`/`free`-Stil ohne Method-Templates.

```cssc
#include('os') os;

method Bounded<int> ?base {
    base!constraints.min = 0;
    base!constraints.max = 100;
} do {} free {};

sector GameState {
private:
    Bounded ! #stack[int, 64] health = 100;
    #stack[int, 32] score = 0;
public:
    object Player<GameState> {   // v6 Default-Ref (legacy `<*GameState>` deprecated)
        takeDamage<int: dmg>:
            GameState->health = GameState->health - dmg;
        heal<int: amount>:
            GameState->health = GameState->health + amount;
        getStatus:
            cssc::out("HP: ");
            cssc::out(GameState->health);
            cssc::out(" Score: ");
            cssc::outln(GameState->score);
    } free {};
} free {
    #delete[health];
    #delete[score];
};

GameState::Player() p;
p.getStatus();
p.takeDamage(30);
p.getStatus();
p.heal(10);
p.getStatus();

#free[GameState];
#free[os];
```

Ausgabe:
```
HP: 100 Score: 0
HP: 70 Score: 0
HP: 80 Score: 0
```

---

## 14. Speicherregeln (Zusammenfassung)

| Was | Wer raeumt auf | Wie |
|-----|---------------|-----|
| `#stack[...] var` | Programmierer | `#delete[var]` |
| `#auto[...] var` | Programmierer | `#delete[var]` |
| `#heap[...] var` | Automatisch | (optional: `#delete[var]`) |
| `sector Name` | Programmierer | `#free[Name]` |
| `object Name` | Programmierer | `#free[Name]` (oder `destruct;` intern) |
| `#include('mod') alias` | Programmierer | `#free[alias]` |
| `#load["file"] alias` | Programmierer | `#free[alias]` oder `#unload[alias]` |
| `Object->member` | Elternobjekt | Im `free {}` Block des Objekts |

---

## 15. CSSC in 40 minuten
10 Tutorials zur Allgemeinheit, 2 Tutorials zu Embedded spezifischer Programmierung

## 15.1 CSSC Tutorial #1 Variablen und Funktionen
----------
**Variablen**
Man deklariert eine Variable immer mit #<MEMTYPE>[<DATATYPE>, <BITSIZE>] VARNAME
MEMTYPES: 'stack' & 'heap'

| DATATYPES | BITSIZES(min)|
|-----------|--------------|
|  integer  |      16      |
|  string   |      32      |
|  vector   |      32      |
|  array    |      32      |
|  bool     |      16      |
|  map      |      40      |
|  bind     |      48      |
|  binary   |      32      |
----------------------------

```cssc
#stack[int, 16] localcounter = 0;
#heap[array<int, string>, ???] = {};
```
Fange an wie ein System zu denken, was braucht der RAM wirklich um diesen array zu halten?
Wir rechnen: Integer (16), String (32), Array (32) + unsere Saftey da wir etwas über das mindeste gehen wollen:
(16 + 32 + 32) = 80 + 1/4 saftey sind 100bits optimal, jetzt die frage: Brauchen wir es nur einmal, mit wenigen Daten oder mehreren Daten?
Wenn du dieses Array nutzen willst, um zbs Viele Daten zu verwalten, willst du viel kapazität für weitere daten haben, indemfall nehmen viele Entwickler
1028 biszu 2048 bits, hierbei empfehle ich einfaches austesten
Du kannst diesen Variabeln auch konkret daten zuwesien:
```cssc
#stack[int, 16] localinteger = 32;
#stack[int, 32] biginteger = 1300000;
#stack[array<int>, 90] cache = {localinteger, biginteger};
```
Und Daten Kontrollieren:
```cssc
if (cache.at(1) > 100) { ... }
select (cache) ?item { ... }
```
Allerdings gillt in CSSC eine sehr spezfische Regel: Wer dreck macht räumt wieder auf.
In CSSC musst du jede einzige allokierte Variable löschen, das machst du mit #delete
```cssc
#delete[cache]; // Cache zuerst, weil es abhängig von localinteger und biginteger ist
#delete[biginteger];
#delete[localinteger];
```
Das etabliert CSSC einen lightweight Compile zu ein minimalen ausführbaren Maschinencode.
Ohne Systeme die dauerhaft analysieren ob etwas RAM sicher ist und nicht zu leaks führt kostet immenzen Overhead
welches auf 80kb Microcontroller absolut unmöglich ist.
 
**Funktionen**
Funktionen sind Variablen mit einem Datenspeicher indem der ausführbare Quellcode ist, den die CPU abarbeitet.
Erst deklarierst du eine Variable, dann weist du ihr einen CPUWorker zu mit #define(<varname>) {}
Das siehst du wenn du diese mal mit `cssc::outln(myfunc)` ausgibst:
> {null, "0x00AE2DF..."}
Es ist eine map aus Berechneter Wert & Workeradresse.
Jedes `myfunc()` startet den Rechencyklus in seinem `{}` und schreibt sein ergebnis in `myfunc[0]`
```cssc
#stack[int, 4] myfunc;
#define(myfunc) {
   #stack[string, 128] msg = 'Hello World';
   cssc::outln(msg);
   #delete[msg];
   return 0; // der return darf nie größer oder ein anderer typ sein, als die original variable ihre deklaration (integer, 4 bits)
}
```
Wenn wir `myfunc` ausgeben bevor wir es einmal überhaupt ausgeführt haben
```cssc
cssc::outln(myfunc);
```
> {null, 029231732832467}
Dann Rufen wir sie auf:
```cssc
myfunc() returnedVal;
```
`myfunc()` löst die Rechnung in myfunc[1] aus und schreibt nach myfunc[0], setzt
du hinter dem `myfunc()` auch einen slot indem es fließen soll, erhälts du eine kopie des Wertes aus myfunc[0]
Setzt du allerdings ein * token davor (ref-token) bekommst du die referenz des berechneten wert, dies wird allerdings
sehr Kompliziert (Dangling Pointers, DeadAdresses, ...) und wird in Tutorial #2 näher erläutert.
Lass uns nochmal nach schauen:
```cssc
cssc::outln(myfunc);
```
> {0, 029231732832467}
Wir sehen, myfunc[0] ist der Berechnete Wert
```cssc
#delete[returnedVal]; // Auch Jede Berechnete variable liegt im RAM und muss gelöscht werden.
#delete[myfunc]; // Jede Variable unterliegt der Regel aufgeräumt zu werden
```
Das öffnet die türen Funktionen nachträglich zu modifzieren
```cssc
#define(switchfuncs) {
   // (from, to)
   // v6 Default-Ref: bare names are TRUE references.
   // Legacy `*f1`/`*f2` is deprecated but still parses as an alias.
   #scanp(switchfuncs, auto, 0) f1;
   #scanp(switchfuncs, auto, 1) f2;
   f2[1] = &f1[1]
   return true;
}
```

---------
## 15.2 CSSC Tutotial #2 Referenze und Kopien
--------
**Die Philosophie von CSSC**
In CSSC gilt standardmäßig das Operation mit Variablen immer zero-copy sind, also ohne das sie geklont werden.
Bedeutet:
```cssc
#stack[int, 16] myage = 19;
#stack[int, 4] isOldEnough;
#define(isOldEnough) {
   #scanp(isOldEnogh, int, 0) age;
   if (age >= 18) { return true; }
   else { 
      mirror false; // mirror beendet nicht
      age = 0;
}
isOldEnough(myage) status;
cssc::outln(status); // true
#stack[int, 16] herage = 17;
isOldEnough(herage) status2;
cssc::outln(status2) // false
cssc::outln(myage)   // 19
cssc::outln(herage)  // 0
```
Um dies zuverhindern nutzt man das '&' token (copy-token) und erzwingt variablen als Kopie zu übergen, diese müssen aber dann auch wieder gelöscht werden:
```cssc
#stack[int, 16] myage = 19;
#stack[int, 4] isOldEnough;
#define(isOldEnough) {
   #scanp(isOldEnogh, int, 0) &age; // Erzwinge aus sicherheit eine Kopie
   if (age >= 18) { mirror true; }
   else { 
      mirror false; // mirror beendet nicht
      age = 0;
   #delete[age];
}
isOldEnough(&myage) status; // Übergbe die Kopie von myage
cssc::outln(status); // true
#stack[int, 16] herage = 17;
isOldEnough(&herage) status2; // Übergebe die Kopie von herage
cssc::outln(status2) // false
cssc::outln(myage)   // 19
cssc::outln(herage)  // 17
```
--------
## 15.3 CSSC Tutorial #3 Der Sektor
--------

**Sektoren**
In CSSC sind Sekoren benannte Scopes (RAII) mit einem cleanup scope am ende. das `free {}`
Sie werden genutzt um Funktionen und Daten in einem Komplexen Container zu Sammeln und zu Ordnen.
### Ausführungsmodell
Bei Sektoren wird zur Interpreterationszeit der innere globale Scope einmal ausgeführt.
```cssc
#stack[int, 32] func;
sector MeinProgramm<func> {   // v6 Default-Ref (legacy `<*func>` deprecated)
   #define(func) { ... }
 } free { #delete[func]; }
```
Sektoren sind Container welche zur  Laufuzeit ansprechbar sind
```cssc
 sector __main__ {
      #stack[string, 128] 0x10000 = 'Hello!';
	cssc::outln(0x10000);
	#stack[int, 4] Myfunc;
	#define(Myfunc) {
	    return 2;
	}
} free {
	#delete[0x10000];
}
 __main__::Myfunc() val;
 cssc::outln(val);
 #delete[val];
```
Du kannst jedes Modell in einen Sektor packen
```cssc
 sector __main__ {
	     object Logic { ... } free { ... };
      Logic() _logic;
} free {
	#delete[_logic];
}
 __main__::Logic() my_new_logic;
 __main__::_logic.func();
 my_new_logics.func();
```
## 15.4 CSSC Tutorial #4 Das Objekt
**Das Objekt**
In CSSC gibt es nicht die typischen klassen (`class`). In C++/Python/Java gibt es immer Klassen-methoden, Klassen-members, destructor und initializer.
In CSSC gibt es das alles auch, aber anders, so das es auf unsere Sprachsemantik zugeschnitten ist, dazu ein konkrete beispiele:
```cssc
object Player {
	#stack[int, 32] Player->health = 100;
} free {
	#delete[Player->health];
}
Player() player_instance1;
Player() player_instance2;
player_instance1->health = 90;
```
Um mit ObjektMembers zu agieren nutzt man `->`. Genau wie bei einem Sektor läuft der innere scope einmal zur laufzeit ab. Um zu kontrollieren was nicht zur laufzeit läuft
nutzt man callpoints, also objekt-gebundene funktionen. diese baut man so auf: `anyname<type: name>:` oder ohne parameter: `anyname:`
```cssc
#stack[int, 32] defualt_start = 0;
object TickCounter<&default_start> {
	 #stack[int, 32] TickCounter->tick = default_start;
	 _tick:
    	 cssc::outln(TickCounter->tick);
	     TickCounter->tick += 1;
} free {
	#delete[TickCounter->tick];
}
TickCounter() tc;
while (true) {
	tc._tick();
}	
```
So kann man sich selbst eine Hardware-orientierte Klasse bauen

```cssc
#depend['item_registery.cssc'] Item_Registery; // Vector hex vergleiche, zbs 0x11 XXX, er schaut nach itemid und gibt zurück, 0x11 029 ist zbs Apfel
sector Player_defaults {
	#stack[int, 32] default_hp = 100;
	#stack[int, 32] default_stamina = 30.0:
	#stack[array<hex>, 256] default_items = {0x11029, 0x11009, 0x11004};
object Player<&Player_defaults, *Item_Registery> {
	#stack[int, 32] Player->HP = Player_defaults::default_hp;
	#stack[int, 32] Player->Stamina = Player_defaults::default_stamina;
	#stack[array<hex>, 1028] Player->Items = Player_defaults::default_items;
	call initialize; // wir rufen direkt bei instanzierung initialize auf
	call register_items;
	initialize:
	   #stack[string ,128] 0x00001e = 'Plyer Instance alive!'
	   cssc::outln(0x00001e);
	   #delete[0x00001e];
	register_items:
	  #stack[bool, 16] status = true
	  select (Player->Items) ?i {
		if (i == 0x0) {
		    break;
		}
	         Item_Registery::Register(i) register_protocoll;
		if (register_protocoll.get_status() == 0xc) {
		    cssc::sleep(1200); // Noch nicht fertig wir warten
		}
		if (register_protocoll.get_status() == 0xf) {
		   status = false; // setze false wenn nicht erfolgreich
		}
		jump;
	}
      if (!status) {
	   mirror false;
	}
	mirror true;
} free { 
	#delete[Player->Player_defaults];
}
Player() newplayer;
Player_defaults::default_items.push_back(0x11001); // zbs Diamanten-items
Player() newplayer_with_diamonds;
```





## 15.5 CSSC Tutorial #5 Die Methode
## 15.6 CSSC Tutorial #6 Module und dependencies
## 15.7 CSSC Tutorial #7 Modulare Systeme
## 15.8 CSSC Tutorial #8 Deine eigenen Module
## 15.9 CSSC Tutorial #9 Deine Erste Anwendung 1/2
## 15.10 CSSC Tutorial #10 Deine Erste Anwendung 2/2
## 15.11 CSSC Tutorial #11 Embedded Programmieren 1/2
## 15.12 CSSC Tutorial #12 Embedded Programmieren 2/2

---

## 16. Backend & Compiler

CSSC ist als Sprache *für* Embedded entworfen — nicht als High-Level-Sprache, die irgendwann später nach C transpiliert wird. Dieses Kapitel beschreibt **wie** der Compiler von `.cssc`-Source zu einem ESP8266-Flash-Image kommt und **warum** das Design auf "C-nahe Performance mit drastisch kleinerer Runtime" zielt.

### 16.1 Pipeline-Überblick

Eine `cssc build script.cssc --esp8266 --flash --port COM3` Invocation läuft durch **7 Phasen**:

```
.cssc Source
    │
    │ 1. Lex + Parse        cssl_cssc.py            (Token-Stream → AST)
    ▼
AST  (Python-Dict-Bäume mit type/line/…)
    │
    │ 2. Lower               cir/cir_lower.py        (AST → CIR-Module)
    ▼
CIR  (typisierte SSA-IR; ~600 Ops für ein 100-Zeilen-Programm)
    │
    │ 3. Codegen — zwei Pfade:
    │     ◦ Host / AVR     → cir_to_llvm.py → LLVM IR
    │     ◦ Xtensa LX106   → transembly/xtensa_lx106.py → .s
    ▼
Assembly / LLVM-IR
    │
    │ 4. Assemble           xtensa-lx106-elf-as / clang -c
    │ 5. Softfloat-Thunks   cssc_softfloat.c → softfloat.o
    │ 6. Link               ld.lld -T esp8266.ld    (Linker-Script ownen wir)
    │ 7. Wrap-Bin           Espressif E9-Magic + Segmente + Checksum
    ▼
firmware.bin   (~17 KB für videodriver.cssc, flashable)
```

Jede Phase ist im Source als eigene Datei isoliert — die Quelle liest sich top-down durch die Pipeline.

### 16.2 Drei Backends, eine Source

| Target | Backend | Pfad |
|--------|---------|------|
| Host (x86_64) | LLVM-IR | `transembly/x86_64.py` → `clang` |
| ESP8266 / ESP32 | Hand-Xtensa-Assembly | `transembly/xtensa_lx106.py` → `xtensa-lx106-elf-as` |
| Arduino (atmega328p) | LLVM-IR | `transembly/avr.py` → `clang --target=avr` |

> **Warum Xtensa per Hand?** Stock-LLVM hat (noch) keinen Xtensa-Backend. Statt einen halben Compiler zu portieren, generiert CSSC direkt `.s` für den `xtensa-lx106-elf` Assembler, den die Espressif-Toolchain mitbringt. Das Hand-Codegen erlaubt zusätzlich **gezielte Optimierungen** (Pair-Align ABI, FPU-Lowering auf LX7, MMIO-Burst-Loops für I2C/SPI) die ein generischer Backend nicht ausnutzen würde.

### 16.3 Speichermodell — Bump-Arena + Scope-Stack

Alle Allokationen — Strings, Vektoren, Maps, Bind-Entries, Object-Instances — laufen durch **einen** Allokator: `cssc_obj_alloc(size)`. Der ist eine reine **Bump-Allocator**: er bewegt nur einen Cursor.

```
   .bss
   ┌────────────────────────────────────────────────────────────┐
   │                  cssc_arena[65536]                          │
   │  ┌──────┬─────────┬──────────┬────────┐                    │
   │  │ obj1 │  obj2   │   obj3   │  obj4  │ ← .. free space ..  │
   │  └──────┴─────────┴──────────┴────────┘                    │
   │                              ↑                              │
   │                       cssc_arena_off (cursor)               │
   └────────────────────────────────────────────────────────────┘
```

Damit der Cursor nicht ewig wächst, hat jeder Funktions-Body (und jede `while`/`for`-Iteration) seine eigene **Scope** — ein gespeicherter Cursor-Snapshot:

```
   scope_push()            cssc_scope_stack[]
   ┌─────────────────┐     ┌────────┐
   │  arena_off=A0   │ ───▶│   A0   │ ← sp
   └─────────────────┘     └────────┘

   …allocations advance cursor to A1…

   scope_pop()             cssc_scope_stack[]
   ┌─────────────────┐     ┌────────┐
   │  arena_off  ←   │ ◀───│   A0   │     sp = sp-1
   │  restored to A0 │     └────────┘
   └─────────────────┘
```

Resultat: **alle** transienten Werte (Float→String-Konvertierungen, String-Concats, intermediäre Bind-Buffer) eines Ticks werden in einer einzigen Instruktion freigegeben — der `cssc_scope_pop`. Kein Refcount-Traversal, kein GC-Pause. Das ist die zentrale Eigenschaft die "Lua-artige Convenience" auf 64 KB Heap überhaupt erst möglich macht.

**Beispiel — ohne / mit Scope:**

```cssc
// ohne Scope (alte Codegen): jeder Tick leakt ~30 Bytes Transients
//   → Arena voll nach ~2000 Ticks (40 Sekunden) → cssc_panic + freeze

// mit Scope (aktuell):
tick:
    display.text(0, 25, cssc::uptime(), tft::WHITE, 1);  // <- alloc transients
    display.show();
}   // <- scope_pop → alle Transients dieses Ticks freigegeben
```

### 16.4 Loop-Scoping

Im selben Geist hat **jede `while`/`for`-Iteration** ihren eigenen Sub-Scope:

```cssc
while (true) {
    vd.tick();
    #stack[float, 64] uptime = cssc::uptime();   // <- in der Iterations-Scope
    if (uptime >= 10.0) break;
}
// ^ Iterations-Scope wird bei jedem Loopback gepoppt — `uptime` und alle
//   transienten Strings darin gehen weg, der Arena-Cursor returnt zur
//   Iterations-Start-Position. Damit läuft die Schleife auch nach
//   1 Million Iterationen ohne Heap-Wachstum.
```

`break` und `continue` poppen den Scope sauber, bevor sie aus der Schleife springen.

### 16.5 Xtensa CALL0-ABI mit Pair-Align

CSSC folgt der **CALL0-Variante** der Xtensa-ABI (keine Window-Rotation, kein Register-Spill-Stack). Argumente gehen in `a2..a7`, mit einer Pair-Alignment-Regel:

| Signatur | Register-Layout |
|----------|----------------|
| `(int)` | a2:a3 |
| `(ptr, int)` | a2 = ptr, a4:a5 = int (a3 ist leer — pair-align) |
| `(int, ptr, int)` | a2:a3 = int, a4 = ptr, a6:a7 = int |
| `(ptr, ptr)` | a2 = ptr, a3 = ptr (kein pair-skip) |

> **Warum Pair-Align?** xtensa-lx106-elf-gcc folgt dieser Konvention für libgcc-Helper. Da CSSC libgcc-Helper (`__muldf3`, `__divdf3`, `__udivsi3`) konsumiert, *muss* die eigene ABI übereinstimmen — sonst kämen f64-Args in den falschen Registern an und jede Float-Operation würde silent korrupt.

Wenn mehr als 6 Register-Slots gebraucht werden, fallen weitere Args auf den Stack — der Function-Prolog liest sie via `l32i.n a8, a1, frame_size + offset` zurück.

### 16.6 Trace-Mode & Diagnostics

Builds mit `--trace` (Default für `cssc diagnostics` auf Chip-Targets) emittieren `> fnname\n` am Function-Entry und `< fnname\n` am Exit:

```
  ┌─ cssc_user_main:
  │  ...prologue...
  │  call0 cssc_print_str        ; ">> cssc_user_main\n"  (via UART0)
  │  ...body...
```

Auf dem Host stitcht `cssc diagnostics` diese Marker zu einem live-Call-Stack zusammen. Wenn die Firmware crasht, weiß das Tool *welche* Funktion zuletzt aktiv war — ohne `addr2line`, ohne ELF, ohne Stack-Walk:

```
$ cssc diagnostics main.cssc --esp8266 --port COM3 --console

CRASH / FAULT DECODES
─────────────────────────────────────
  Crash #1  ×1  (first @ 3.21s)
    cause       : LoadProhibitedCause (load from non-readable region)
    epc1 (PC)   : 0x40001800
    excvaddr    : 0x00000007  (low-memory — small int used as pointer)

    TRACE — the call chain the chip was inside when it crashed:
      └─ cssc_user_main  (entered @ 0.001s)
        └─ cssc_obj_VideoDriver_tick  (entered @ 3.140s)
          └─ cssc_array_bind_push_entry  (entered @ 3.210s)
        → innermost frame at crash: cssc_array_bind_push_entry
          (still running 0.5 ms after entry)
```

`cssc diagnostics --dev` ergänzt das mit einem **statischen Framework-Audit**: liest die Backend-Source-Tree und sucht nach ABI-Mismatches, fehlenden Scope-Pins in Runtime-Helpern, ungültiger Ctor-Bindings-Reihenfolge, und User-Code-Smells (use-after-delete, wrong-arity overloads). Siehe [cssl_dev_audit.py](../../core/cssl/cssl_dev_audit.py).

### 16.7 Performance — gleiche C-Geschwindigkeit, viel kleinere Runtime

Die Designentscheidungen oben sind nicht zufällig — sie zielen auf **C-Performance ohne C-Boilerplate**. Ein typisches Render-Tick auf ESP8266:

| Pipeline | Tick-Dauer | Tick-Frequenz | Bin-Size |
|---------|----------:|:----:|:----:|
| Hand-C + ESP-IDF | ~52 ms | 19 Hz | ~12 KB |
| **CSSC v6 native** | **~55 ms** | **18 Hz** | **~17 KB** |
| Arduino-Framework C++ | ~70 ms | 14 Hz | ~190 KB |
| MicroPython | ~480 ms | 2 Hz | ~600 KB + Python-Heap |

> Messungen: `videodriver.cssc` auf NodeMCU @ 80 MHz, OLED 128×64 SSD1306 via I2C 400 kHz, Frame mit Uptime-Float-Print + Bouncing-Box. Tick-Dauer wurde mit `cssc::tick()` zwischen Anfang und Ende des `tick:`-Labels gemessen.

Die **~6 % Overhead vs Hand-C** kommen aus Softfloat-Helpern (`__muldf3` etc. — ESP8266 hat keine Hardware-FPU) und CALL0-ABI-Bewegungen, NICHT aus Compiler-Indirection. Die `.bin` ist 5 KB größer als Hand-C, weil der Bump-Arena-Allokator + Scope-Stack-Runtime + Print-Helper mit eingelinkt sind — alle bezahlt einmalig, nicht pro Funktionsaufruf.

**Im Vergleich zu Script-VMs (MicroPython/Lua):** ~9× schneller, ~35× kleiner Bin. Weil CSSC eben *kompiliert* — der Tick führt nativen Xtensa-Code aus, nicht Bytecode-Dispatch.

### 16.8 Was implementiert ist (Stand v6)

| Feature | Native (`cssc build`) | Interpreter (`cssc run`) | Notiz |
|---------|:--:|:--:|------|
| Primitive (`int/float/bool/string`) | ✅ | ✅ | float strikt ≥ 64-bit auf native |
| Container (`vector/array/map/bind`) | ✅ | ✅ | `select` nur über `vector<int>` + `array<bind>` |
| `#define` / `#cdefine` | ✅ | ✅ | |
| `#redefine` | ❌ | ✅ | Statische Kompilierung — AST-Mutation no-op |
| `object` + Labels + `mirror` | ✅ | ✅ | Label-Parameter-Bodies ja, parametrisierte Method-Templates noch nicht |
| Ref-Capture `<*x>` | ✅ | ✅ | |
| `select` / `jump` | ✅ | ✅ | |
| Sektoren (`#define(Sec->fn)`) | ✅ | ✅ | |
| `#load` / `#unload` | ❌ | ✅ | Laufzeit-Modulauflösung passt nicht zu Static-Linking |
| `#daemon` / `#killdaemon` | ❌ | ✅ | FreeRTOS-Mapping auf ESP32 in Phase 6 geplant |
| `#thread` | ❌ | ✅ | Wie `#daemon` |
| `#catch` | ⚠️ | ✅ | Native: setjmp/longjmp; nur `cssc_panic` ist catchable |
| Embedded-Peripherie (GPIO/I2C/SPI/OLED/TFT) | ✅ | ❌ (simuliert) | Host-Interpreter hat keine reale Hardware |

Wo eine Direktive auf einem Backend nicht implementiert ist, produziert die Lower-Phase einen klaren `CIR-Lower Error` mit Phase-Hinweis — kein silent skip.

---

## Danke für die Aufmerksamkeit

*CSSC v6.0 — Designed by Lilias Hatterscheidt*
*established by IncludeCPP Framework*
