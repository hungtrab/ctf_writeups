# escape_room — detailed write-up

- **Challenge**: `challenge`
- **Category**: `rev`
- **Binary**: `./escaperoom`
- **Flag**: `CIT{Vc282vlhCxIJ}`

---

## 1. Initial triage

First I listed the workspace and checked the target binary.

```bash
pwd
ls -la
find ./files -maxdepth 3 -type f -printf '%p\n' | sort
file ./escaperoom
```

### Observation

`escaperoom` is:

- **ELF 64-bit**
- **statically linked**
- **not stripped**

That combination is good for reversing because:

- static means large binary / lots of library noise,
- not stripped means internal function names still exist.

---

## 2. Quick strings pass

I searched for useful strings.

```bash
strings -a ./escaperoom | grep -aE 'CIT\{|flag|FLAG|correct|wrong|congrat|password|token|override|accepted|denied|granted|invalid|access|maintenance|svc|staged|alarm|speaker|reset|unlock|door|mirror|hush|decode'
```

### Important strings found

These were the most useful hints:

- `Tip: maintenance logs may be dirty, reflected, or rotated.`
- `[ops/07] Corridor override refuses to arm while hallway lights are ON.`
- `[patch/02] Apply the door patch twice. The third write trips watchdog.`
- `[svc/01] Mirror first. Then hush.`
- `hush   -> mute alarm speaker if the room is staged correctly`
- `[svc] mirror relay aligned. inspection mode enabled.`
- `[svc] alarm speaker muted.`

### Observation

Even before disassembly, the strings strongly suggested:

- this is a **room-state puzzle**, not just a single hardcoded password,
- the correct state likely depends on multiple menu actions,
- **mirror** and **hush** are maintenance-shell commands,
- text in logs may need reflection/rotation interpretation,
- lights must probably be **OFF**,
- patch count probably must be exactly **2**.

---

## 3. Symbol discovery

Because the binary is not stripped, I enumerated symbols.

```bash
nm -C ./escaperoom | grep -E ' main$|validate|buildOverrideToken|roomAligned|roomSignature|enterOverrideToken|maintenance'
```

### Key symbols

```text
0000000000409997 T main
0000000000409300 T validate(std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> > const&)
0000000000408efd t roomAligned()
0000000000408f5f t roomSignature()
0000000000409011 t buildOverrideToken()
00000000004096ed t enterOverrideToken()
0000000000408902 t maintenanceConsole()
0000000000579ec0 r validate(...)::enc
0000000000579e60 r buildOverrideToken()::spice
```

### Observation

This immediately revealed the intended structure:

- `roomAligned()` checks whether the puzzle state is correct,
- `roomSignature()` computes a 32-bit state-dependent value,
- `buildOverrideToken()` turns that into the token the terminal wants,
- `validate()` probably checks the user input and returns either a denial message or the flag,
- `enterOverrideToken()` prints the return value of `validate()`.

---

## 4. Running the program

The file initially was not executable, so I fixed that and ran it.

```bash
chmod +x ./escaperoom
printf '9\n0\n' | ./escaperoom
```

The program presents this menu:

```text
1. read facility log
2. toggle hallway lights
3. cycle ventilation route
4. rotate camera bus
5. apply door-control patch
6. toggle emergency battery bridge
7. maintenance shell
8. enter door override token
9. status
0. quit
```

### Observation

The binary is a state machine controlled by menu actions.

From the menu and strings, the mutable state appears to include:

- hallway lights
- ventilation route
- camera bus
- patch count
- battery bridge
- maintenance-only flags such as `mirror` and `hush`

---

## 5. Reversing `roomAligned()`

Disassembly:

```bash
objdump -d -M intel --start-address=0x408efd --stop-address=0x409300 ./escaperoom
```

### Relevant logic

`roomAligned()` checks the global state structure at `g_state`:

```asm
movzx  eax,BYTE PTR [g_state]        ; lights bit
xor    eax,0x1
...
cmp    DWORD PTR [g_state+0x4],0x1   ; ventilation
...
cmp    DWORD PTR [g_state+0x8],0x3   ; camera
...
cmp    DWORD PTR [g_state+0xc],0x2   ; patch count
...
test   BYTE PTR [g_state+0x10]       ; battery bridge
...
test   BYTE PTR [g_state+0x11]       ; mirror flag
...
test   BYTE PTR [g_state+0x12]       ; hush flag
```

### Recovered conditions

`roomAligned()` returns true only if all of these are satisfied:

1. **hallway lights = OFF**
2. **ventilation route = 1**
3. **camera bus = 3**
4. **door patch count = 2**
5. **battery bridge = ON**
6. **mirror flag = set**
7. **hush flag = set**

### Important correction

This was the key place where my earlier manual assumptions were slightly wrong.

I originally tried:

- vent = 3
- camera = 2

But the actual aligned values from the disassembly are:

- **vent = 1**
- **camera = 3**

Since the program starts from zeroed/default state, that means:

- toggle lights once,
- cycle vents once,
- rotate cameras three times,
- patch twice,
- enable battery bridge,
- in maintenance shell: `mirror`, then `hush`.

---

## 6. Reversing `roomSignature()`

Still in the same disassembly block, `roomSignature()` computes a 32-bit state-dependent signature.

### Recovered pseudocode

```cpp
uint32_t roomSignature() {
    uint32_t s = 0xA17C3E29;

    s ^= lights ? 0x13579BDF : 0x2468ACE0;
    s = rol32(s, 7);

    s += (vent + 1)   * 0x1F123BB5;
    s ^= (camera + 3) * 0x045D9F3B;
    s += (patch + 5)  * 0x27D4EB2D;

    s ^= battery ? 0xA5A55A5A : 0x5A5AA5A5;
    s += mirror  ? 0x31415926 : 0x27182818;
    s ^= hush    ? 0xDEADBEEF : 0xBAD0C0DE;

    return s;
}
```

### Observation

This means the override token is not fixed globally; it depends on the exact room state. So even if the token builder is recovered, the token is only valid for the right staged configuration.

---

## 7. Reversing `buildOverrideToken()`

Disassembly:

```bash
objdump -d -M intel --start-address=0x409011 --stop-address=0x409220 ./escaperoom
```

### Constants extracted from `.rodata`

I dumped the relevant constants directly:

```bash
python3 - <<'PY'
from pathlib import Path
b=Path('escaperoom').read_bytes()
base_va=0x579000
base_off=0x179000
for va,size,name in [
    (0x579e60, 32, 'spice'),
    (0x579ec0, 13, 'enc')
]:
    off=base_off+(va-base_va)
    chunk=b[off:off+size]
    print(name, hex(va), chunk.hex())
PY
```

Output:

```text
spice 0x579e60 1300000037000000dec00000efbe00005a000000ce0a0000424200000d900000
enc   0x579ec0 19130e210c396862682c363219
```

The `spice` table decodes as little-endian 32-bit values:

```python
spice = [
    0x13,
    0x37,
    0xC0DE,
    0xBEEF,
    0x5A,
    0x0ACE,
    0x4242,
    0x900D,
]
```

The alphabet comes from rodata string construction inside `buildOverrideToken()`:

```text
ABCDEFGHJKLMNPQRSTUVWXYZ23456789
```

### Recovered algorithm

From the assembly, the logic is:

1. `seed = roomSignature() ^ 0x6f70656e`
   - `0x6f70656e` is ASCII `"open"`
2. Build a 10-character token
3. For each character:
   - `seed = seed * 0x19660d`
   - `seed += spice[i]`
   - `seed += 0x3c6ef35f`
   - `idx = seed >> 27`
   - output `alphabet[idx]`
4. Insert `-` after characters 3 and 6

### Recovered Python

```python
alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
spice = [0x13, 0x37, 0xC0DE, 0xBEEF, 0x5A, 0x0ACE, 0x4242, 0x900D]

def rol32(x, r):
    return ((x << r) | (x >> (32-r))) & 0xffffffff

def room_signature(lights, vent, camera, patch, battery, mirror, hush):
    s = 0xA17C3E29
    s ^= 0x13579BDF if lights else 0x2468ACE0
    s = rol32(s, 7)
    s = (s + ((vent + 1) * 0x1F123BB5)) & 0xffffffff
    s ^= ((camera + 3) * 0x045D9F3B) & 0xffffffff
    s = (s + ((patch + 5) * 0x27D4EB2D)) & 0xffffffff
    s ^= 0xA5A55A5A if battery else 0x5A5AA5A5
    s = (s + (0x31415926 if mirror else 0x27182818)) & 0xffffffff
    s ^= 0xDEADBEEF if hush else 0xBAD0C0DE
    return s & 0xffffffff

def build_token(sig):
    x = sig ^ 0x6f70656e
    out = []
    for i in range(10):
        x = (x * 0x19660d + spice[i % len(spice)] + 0x3c6ef35f) & 0xffffffff
        out.append(alphabet[x >> 27])
    return ''.join(out[:3]) + '-' + ''.join(out[3:6]) + '-' + ''.join(out[6:])
```

### Token for the aligned state

For the correct aligned state:

- lights = OFF = `0`
- vent = `1`
- camera = `3`
- patch = `2`
- battery = `1`
- mirror = `1`
- hush = `1`

The generated token is:

```text
RHY-QVT-KAXJ
```

This is the exact token that worked.

---

## 8. About `validate()`

`validate()` has a symbol, but the body is intentionally awkward to read in a straight `objdump` pass. The function entry jumps into a region that disassembles like garbage/inlined data when viewed linearly:

```asm
0000000000409300 <validate(...)>:
  409300: e9 68 34 70 00    jmp ...
```

### Observation

This strongly suggests the author deliberately made the validation routine annoying to statically read using a simple linear disassembler view.

However, this challenge did **not** require fully deobfuscating `validate()` because:

- `enterOverrideToken()` clearly passes user input into `validate()`,
- then prints the returned string,
- and once the correct state + token were supplied, the function returned the flag string directly.

In other words, the clean path to solve was:

1. reverse the room-state checks,
2. reverse the token generator,
3. stage the room exactly,
4. submit the generated token.

That was enough to make `validate()` yield the flag.

---

## 9. Reversing `enterOverrideToken()`

Disassembly:

```bash
objdump -d -M intel --start-address=0x4096ed --stop-address=0x409819 ./escaperoom
```

### Key logic

`enterOverrideToken()` does the following:

1. prints `override token> `
2. reads a full line from stdin,
3. calls `validate(user_input)`
4. prints the returned string

### Important observation

This explains the final behavior perfectly.

When the solve path is correct, the terminal prints:

```text
override token> CIT{Vc282vlhCxIJ}
```

That means `validate()` itself returned the flag string for the successful input.

---

## 10. Dynamic probing of the menu logic

Before the final solve, I used direct scripted interaction to learn how menu actions affected state.

Examples:

```bash
printf '9\n0\n' | ./escaperoom
printf '5\n5\n4\n7\nmirror\nback\n6\n7\nhush\ndecode\nback\n8\nRHY-QVT-KAXJ\n0\n' | ./escaperoom
printf '2\n3\n3\n3\n4\n4\n5\n5\n6\n7\nmirror\nhush\ndecode\nback\n8\nRHY-QVT-KAXJ\n0\n' | ./escaperoom
```

### Observations from runtime

- `mirror` only works once the camera bus reaches the mirror relay path.
- `hush` only succeeds once the room is staged properly enough.
- patch count matters exactly: two patches are accepted, a third would be wrong per hint.
- lights definitely must be OFF.
- the earlier attempt with vent/camera assumptions swapped failed, confirming that static `roomAligned()` analysis was the authoritative answer.

---

## 11. Exact successful interaction sequence

Starting from the default state, the correct actions are:

1. `2` → turn **hallway lights OFF**
2. `3` → set **vent route = 1**
3. `4` → camera bus 1
4. `4` → camera bus 2
5. `4` → camera bus 3 (**mirror relay**)
6. `5` → patch layer 1
7. `5` → patch layer 2
8. `6` → engage **battery bridge**
9. `7` → open maintenance shell
10. `mirror`
11. `hush`
12. `decode` (optional, just confirms hints)
13. `back`
14. `8` → enter override token
15. `RHY-QVT-KAXJ`

The exact command I used:

```bash
printf '2\n3\n4\n4\n4\n5\n5\n6\n7\nmirror\nhush\ndecode\nback\n8\nRHY-QVT-KAXJ\n0\n' | ./escaperoom
```

### Output

Relevant tail of the output:

```text
[svc] mirror relay aligned. inspection mode enabled.
[svc] alarm speaker muted.
[decode] [patch/02] Apply the door patch twice. The third write trips watchdog.
[decode] [svc/01] Mirror first. Then hush.
[decode] inspection confirms reflected and rotated maintenance text paths.
...
override token> CIT{Vc282vlhCxIJ}
```

---

## 12. Final answer

```text
CIT{Vc282vlhCxIJ}
```

---

## 13. Short solve summary

The challenge is a menu-driven room-state puzzle.

The solve path was:

- inspect strings and symbols,
- reverse `roomAligned()` to recover the **exact required state**,
- reverse `roomSignature()` and `buildOverrideToken()` to compute the **correct token** for that state,
- interact with the menu to stage the room,
- submit the computed token,
- receive the flag from `validate()`.

### Final recovered values

- Required state:
  - lights = OFF
  - vent = 1
  - camera = 3
  - patch = 2
  - battery = ON
  - mirror = set
  - hush = set
- Generated token: `RHY-QVT-KAXJ`
- Flag: `CIT{Vc282vlhCxIJ}`
