# IncludeCPP

Use C++ code in Python. Write your C++ functions and classes, IncludeCPP generates the Python bindings automatically.

```bash
pip install IncludeCPP
```

## Quick Start

### 1. Create a Project

```bash
mkdir myproject && cd myproject
includecpp init
```

This creates:
- `cpp.proj` - your project settings
- `include/` - put your C++ files here
- `plugins/` - binding files go here (auto-generated)

### 2. Write Some C++

Create `include/math.cpp`:

```cpp
namespace includecpp {

int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    return a * b;
}

}
```

Your code must be inside `namespace includecpp`. Everything outside is ignored.

### 3. Generate Bindings

```bash
includecpp plugin math include/math.cpp
```

This scans your C++ and creates `plugins/math.cp` with the binding instructions.

### 4. Build

```bash
includecpp rebuild
```

Compiles your C++ into a Python module.

### 5. Use in Python

```python
from includecpp import math

print(math.add(2, 3))       # 5
print(math.multiply(4, 5))  # 20
```

Done. Your C++ code works in Python.

---

## Classes

C++ classes work the same way:

```cpp
// include/calculator.cpp
#include <vector>

namespace includecpp {

class Calculator {
public:
    Calculator() : result(0) {}

    void add(int x) { result += x; }
    void subtract(int x) { result -= x; }
    int getResult() { return result; }
    void reset() { result = 0; }

private:
    int result;
};

}
```

Generate and build:

```bash
includecpp plugin calculator include/calculator.cpp
includecpp rebuild
```

Use in Python:

```python
from includecpp import calculator

calc = calculator.Calculator()
calc.add(10)
calc.add(5)
calc.subtract(3)
print(calc.getResult())  # 12
```

---

## Development Workflow

When you're actively working on your C++:

```bash
# Regenerate bindings AND rebuild in one command
includecpp auto math

# Fast rebuild (skips unchanged files, ~0.4s when nothing changed)
includecpp rebuild --fast

# Rebuild everything from scratch
includecpp rebuild --clean
```

---

## CLI Commands

| Command | What it does |
|---------|-------------|
| `init` | Create project structure |
| `plugin <name> <file.cpp>` | Generate bindings from C++ |
| `auto <name>` | Regenerate bindings + rebuild |
| `rebuild` | Compile all modules |
| `rebuild --fast` | Fast incremental build |
| `rebuild --clean` | Full clean rebuild |
| `get <name>` | Show module's API |
| `server start` | Start HomeServer |
| `server stop` | Stop HomeServer |
| `server upload` | Upload file/project |
| `server download` | Download file/project |
| `server list` | List stored items |

---

## Project Configuration

The `cpp.proj` file controls your build:

```json
{
  "project": "MyProject",
  "include": "/include",
  "plugins": "/plugins",
  "compiler": {
    "standard": "c++17",
    "optimization": "O3"
  }
}
```

---

## Plugin Files (.cp)

The `.cp` files tell IncludeCPP what to expose. They're auto-generated, but you can edit them:

```
SOURCE(calculator.cpp) calculator

PUBLIC(
    calculator CLASS(Calculator) {
        CONSTRUCTOR()
        METHOD(add)
        METHOD(subtract)
        METHOD(getResult)
        METHOD(reset)
    }
)
```

Common directives:
- `CLASS(Name)` - expose a class
- `METHOD(name)` - expose a method
- `FUNC(name)` - expose a function
- `FIELD(name)` - expose a member variable
- `CONSTRUCTOR()` or `CONSTRUCTOR(int, string)` - expose constructor

---

## Requirements

- Python 3.9+
- C++ compiler (g++, clang++, or MSVC)
- CMake

pybind11 is installed automatically.

---

## More Help

```bash
includecpp --doc           # Full documentation
includecpp --changelog     # Version history
includecpp <command> --help
```

---

## HomeServer

Store and manage your modules, projects and files locally with the HomeServer:

```bash
# Install and start the server (one-time setup)
includecpp server install

# Manual start/stop
includecpp server start
includecpp server stop
includecpp server status

# Upload files or projects
includecpp server upload mymodule ./include/mymodule.cpp
includecpp server upload myproject ./myproject --project

# List, download, delete
includecpp server list
includecpp server download mymodule ./backup/
includecpp server delete mymodule

# Change port (default: 2007)
includecpp server port 3000

# Remove HomeServer completely
includecpp server deinstall
```

The server runs silently in the background and can auto-start with Windows.

---

## CSSL Scripting Language

CSSL is IncludeCPP's built-in scripting language with 330+ builtin functions, C++-style syntax, and advanced features like CodeInfusion and BruteInjection.

### Quick Example

```bash
# Run CSSL code
includecpp cssl run "printl('Hello from CSSL!');"

# Run a .cssl file
includecpp cssl file script.cssl

# Interactive REPL
includecpp cssl repl
```

### Features

- **C++ Containers**: `vector<T>`, `stack<T>`, `map<K,V>`, `queue<T>`, `datastruct<T>`
- **Classes & Inheritance**: `class Child : extends Parent { }`
- **Namespaces & Enums**: Organize code with `namespace mylib { }`
- **CodeInfusion**: Inject code into functions at runtime with `<<==`
- **BruteInjection**: Data manipulation with `<==` and filters
- **Snapshots**: Capture and restore variable states with `%variable`
- **C++ I/O Streams**: `cout << "Hello" << endl;`
- **Native/Unative**: Control C++/Python execution with keywords

### CSSL CLI

```bash
includecpp cssl run "code"     # Execute code string
includecpp cssl file script.cssl  # Run .cssl file
includecpp cssl repl           # Interactive mode
includecpp cssl convert file.cssl  # Convert to Python
includecpp cssl docs           # Full documentation
```

Full documentation: `includecpp cssl docs` or see [CSSL_DOCUMENTATION.md](includecpp/core/cssl/CSSL_DOCUMENTATION.md)

---

## Experimental Features

IncludeCPP also includes experimental features:

- **AI Commands** - OpenAI-powered code analysis (`includecpp ai`)
- **CPPY** - Python to C++ conversion (`includecpp cppy`)

Enable with: `includecpp settings` → "Enable Experimental Features"

---

## Issues

Report bugs at: https://github.com/liliassg/IncludeCPP/issues

```bash
includecpp bug    # Quick bug report
includecpp update # Update to latest version
```
