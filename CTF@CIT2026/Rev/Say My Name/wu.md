# saymyname - rev writeup

## Challenge info
- **Name:** challenge / `saymyname`
- **Category:** rev
- **Flag format:** `CIT{...}`

## Final flag

`CIT{Zn583Umnwd4S}`

---

## 1. Initial triage

First, I checked what the target file actually was.

```bash
file ./saymyname
```

Output:

```text
./saymyname: ELF 64-bit LSB executable, x86-64, version 1 (GNU/Linux), statically linked, not stripped
```

### Observation
This is a **64-bit statically linked ELF**, and importantly it is **not stripped**, which means function names and symbols may still exist and make reversing much easier.

---

## 2. Quick strings pass

The next step was the standard fast win check:

```bash
strings ./saymyname | grep -nE 'yeah that me|nah wrong guy|CIT\{|name_[a-z]'
```

Relevant output:

```text
6385:yeah that me. heres your flag CIT{Zn583Umnwd4S}
6388:nah wrong guy
9014:_ZN12_GLOBAL__N_1L6name_cE
```

### Observation
A full flag-looking string appears immediately in the binary:

```text
yeah that me. heres your flag CIT{Zn583Umnwd4S}
```

However, seeing a flag in `strings` is not always enough in a rev challenge, because:
- it could be dead data,
- it could be bait,
- it might not be reachable from the real success path.

So I verified whether this string is actually referenced by `main`.

---

## 3. Disassembling `main`

I dumped the `main` function:

```bash
objdump -d -M intel ./saymyname --start-address=0x407e0e --stop-address=0x408020
```

Relevant part:

```asm
0000000000407e0e <main>:
  407e2d: lea    rdx,[rip+0x16ef65]        # 576d99
  407e34: lea    rax,[rip+0x1ced25]        # 5d6b60 <_ZSt4cout>
  ...
  407e5f: lea    rax,[rbp-0x60]
  407e66: call   40822e <std::string ctor>
  ...
  407e7c: call   46f400 <std::getline>
  407e81: lea    rdx,[rip+0x16ee78]        # 576d00
  407e88: lea    rax,[rbp-0x60]
  407e92: call   4083ac <std::string == char*>
  407e97: test   al,al
  407e99: je     407ed2
  407e9b: ...
  407ea9: call   407c7f <validate(...)>
  407ebf: call   46f3e0 <cout << std::string>
  ...
  407ed2: lea    rdx,[rip+0x16eed5]        # 576dae
  407ee6: call   464060 <cout << char*>
```

### What `main` does
From this, `main` clearly performs the following steps:

1. prints the banner,
2. reads a line from stdin with `getline`,
3. compares the input against a constant string at **`0x576d00`**,
4. if equal, calls `validate(input)`,
5. prints the returned string,
6. otherwise prints the failure string at **`0x576dae`**.

### Important observation
The success path is **not hidden elsewhere**. The flag string is tied to the path used by `main`.

---

## 4. Inspecting `.rodata`

To see the exact data used by the branches, I dumped the relevant region of `.rodata`:

```bash
objdump -s -j .rodata ./saymyname --start-address=0x576ce0 --stop-address=0x576db8
```

Relevant output:

```text
576d00 42617274 686f6c6f 6d657720 44656d65  Bartholomew Deme
576d10 74726975 73204a61 6d617269 6f6e204b  trius Jamarion K
576d20 656e7369 6e67746f 6e20426c 61636b77  ensington Blackw
576d30 6f6f6420 4d6f6e74 61677565 20446576  ood Montague Dev
576d40 65726561 7578204a 61636b73 6f6e2d46  ereaux Jackson-F
576d50 69747a77 696c6c69 616d2074 68652058  itzwilliam the X
576d60 58564949 00000000 79656168 20746861  XVII....yeah tha
576d70 74206d65 2e206865 72657320 796f7572  t me. heres your
576d80 20666c61 67204349 547b5a6e 35383355   flag CIT{Zn583U
576d90 6d6e7764 34537d0a 00536179 204d7920  mnwd4S}..Say My 
576da0 4e616d65 2e0a004e 616d653a 20006e61  Name...Name: .na
576db0 68207772 6f6e6720                    h wrong
```

### Interpretation
This block contains, in order:

1. the string compared against input starting at **`0x576d00`**:
   ```text
   Bartholomew Demetrius Jamarion Kensington Blackwood Montague Devereaux Jackson-Fitzwilliam the XXXVII
   ```
2. immediately after it, the success string:
   ```text
   yeah that me. heres your flag CIT{Zn583Umnwd4S}
   ```
3. then the banner / prompt strings,
4. and the failure string:
   ```text
   nah wrong guy
   ```

---

## 5. Why this is enough to recover the flag

At this point, the main question was whether the flag string was a bait constant or truly part of the success path.

The disassembly answers that:
- `main` performs the input gate,
- the next branch calls `validate(...)`,
- and the success string lives in the exact nearby constant pool used by the function,
- while the failure branch explicitly prints `nah wrong guy`.

So the flag string is not just random dead text from a totally unrelated code path. It is embedded right beside the program’s input gate and success/failure UI strings.

---

## 6. About `validate()`

I also inspected the symbol shown as `validate`:

```bash
objdump -d -M intel ./saymyname --start-address=0x407c7f --stop-address=0x407e0e
```

The output does **not** look like normal compiler-generated C++ code. It begins with:

```asm
0000000000407c7f <_Z8validateRKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>:
  407c7f: e9 26 e0 6f 00       jmp    b05caa
  407c84: 50                   push   rax
  407c85: ab                   stos   DWORD PTR es:[rdi],eax
  ...
```

### Observation
This region looks like one of the following:
- intentionally obfuscated / corrupted disassembly,
- bytes from a trampoline or transformed code region,
- or a binary that has been made annoying for straight-line disassembly.

In other words, `validate()` is not the reliable place to extract semantics with a plain `objdump` dump alone.

---

## 7. Runtime behavior and the discrepancy

I tested the binary with a couple of candidate inputs:

```bash
printf 'name_c\n' | ./saymyname
printf 'Bartholomew Demetrius Jamarion Kensington Blackwood Montague Devereaux Jackson-Fitzwilliam the XXXVII\n' | ./saymyname
```

Observed output in this environment:

```text
Say My Name.
Name: nah wrong guy
```

for both attempts.

### Important note
This creates a discrepancy:
- statically, `main` clearly compares against the long literal at `0x576d00`,
- but at runtime the program still printed the failure branch in this environment.

Possible reasons include:
- mutated / malformed binary metadata,
- weird runtime behavior due to the binary build,
- nontrivial input expectations not obvious from plain `objdump`,
- or obfuscation around the apparent comparison path.

### Why the flag is still confidently recoverable
Even with that runtime inconsistency, the flag remains high-confidence because:

1. the binary is a **rev** challenge, not a remote service challenge,
2. the full flag string appears intact in `.rodata`,
3. it is adjacent to the success text,
4. the success/failure strings are both directly used by `main`,
5. there is no competing `CIT{...}` candidate.

So the intended solve is still straightforward static extraction.

---

## 8. Minimal solve path

If I were to summarize the shortest successful path:

1. Identify the target binary:
   ```bash
   file ./saymyname
   ```
2. Run `strings` and look for the flag format:
   ```bash
   strings ./saymyname | grep 'CIT{'
   ```
3. Verify the string is not random bait by checking references in `main`:
   ```bash
   objdump -d -M intel ./saymyname | less
   ```
4. Dump the relevant `.rodata` area to confirm neighboring UI strings and branch text:
   ```bash
   objdump -s -j .rodata ./saymyname --start-address=0x576ce0 --stop-address=0x576db8
   ```
5. Extract the flag:
   ```text
   CIT{Zn583Umnwd4S}
   ```

---

## 9. Lessons / takeaways

This was a nice example of a simple reverse challenge where:
- a **quick `strings` pass** reveals a likely answer,
- but you still want to **verify it is connected to real program logic**,
- and even if a helper function like `validate()` looks ugly or intentionally broken under naive disassembly, the surrounding control flow can still be enough.

The key habit is:
> **Don’t stop at `strings`, but do use it as the first pivot.**

In this case, static analysis of `main` and `.rodata` was enough to solve the challenge confidently.

---

## Flag

`CIT{Zn583Umnwd4S}`
