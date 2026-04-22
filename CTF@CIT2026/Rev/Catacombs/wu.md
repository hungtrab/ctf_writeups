# catacombs — rev writeup

## Challenge overview
- **Name:** challenge
- **Category:** rev
- **Binary:** `./catacombs`
- **Flag format:** `CIT{}`

This challenge is a static, non-stripped ELF that presents itself as an interactive “syscall trace harness”.
At first glance it contains a flag-looking string directly in `.rodata`, but the binary is intentionally designed to make that look suspicious.
The core reversing task is to recover the **valid syscall sequence** that reaches the accepting state.

---

## 1. Initial triage

The provided `files/` directory was empty, so the real target was the top-level binary.

### Command
```bash
file ./catacombs
```

### Observation
```text
./catacombs: ELF 64-bit LSB executable, x86-64, statically linked, not stripped
```

This was already a good sign for reversing:
- static binary
- symbols still present
- likely solvable from strings + disassembly

---

## 2. Quick string scan

### Command
```bash
strings -a ./catacombs | grep -Ein 'CIT\{|FLAG_BAIT_LABEL|syscall-lit|coherent trace|openat|read|mmap|ioctl|futex|clone|close|ACCESS GRANTED|ACCESS DENIED'
```

### Important hits
```text
openat
read
mmap
ioctl
futex
clone
close
[catacombs] syscall-lit ossuary trace harness
[catacombs] descend through the buried mesh and submit a coherent trace
chalk scrape: burial ledger from the ring buffer -> openat x2, read x2, mmap x1, ioctl x2, futex x1, clone x1, close x1
grave note: the sanctum only accepts close() when entered from sysproxy
field report: two openat calls bracket the fork path; futex is not the finale
CIT{3R2rA2J0PdFH}
ACCESS GRANTED:
ACCESS DENIED
```

### Observation
There is a literal flag-looking string:
```text
CIT{3R2rA2J0PdFH}
```

However, that alone is not enough to trust it. In CTF rev challenges, a direct embedded flag string is often a decoy.
Later, symbol inspection confirmed this suspicion because the binary exposes a label named `FLAG_BAIT_LABEL`.

So at this point my conclusion was:
- the embedded `CIT{...}` may be real or bait,
- I need to recover the actual validation logic before trusting it.

---

## 3. Run the binary and inspect the UI

### Command
```bash
./catacombs
```

### Output
```text
[catacombs] syscall-lit ossuary trace harness
[catacombs] descend through the buried mesh and submit a coherent trace
type 'help' for commands
```

This showed it was not a one-shot checker. It is an **interactive interpreter**.

### Built-in help
```bash
printf 'help
status
hint
notice-check
bait
submit
' | timeout 3s ./catacombs
```

### Output
```text
commands:
  help                 show commands
  status               show visible state
  hint                 print a rotating hint
  step <syscall>       apply one syscall transition
  script a b c         apply multiple syscalls
  reset                reset the trace
  submit               call validate()
  bait                 print the visible bait label
  notice-check         reference the integrity notice without dumping it

node        : 0 (mouth)
steps       : 0/16
acc         : 0xa17c39d4
breadcrumb  : 0xc3b5da91
mix         : 0x4d415a452d4c4142
cookie      : 0xe1b9a7c33d55aa11
trace       : <empty>

chalk scrape: burial ledger from the ring buffer -> openat x2, read x2, mmap x1, ioctl x2, futex x1, clone x1, close x1
notice loaded: yes, bytes: 1395
bait label: flag
ACCESS DENIED
```

### Observation
The important information from the UI:
1. The program wants a sequence of syscalls, applied via `step` or `script`.
2. `hint` already leaks the required **multiset** of operations:
   - `openat x2`
   - `read x2`
   - `mmap x1`
   - `ioctl x2`
   - `futex x1`
   - `clone x1`
   - `close x1`
3. `bait` prints only `flag`, not the `CIT{...}` string.
4. `submit` calls a validator after the trace is built.

So the problem became:
- recover how each syscall changes state,
- determine the only valid order.

---

## 4. Confirm the embedded flag is suspicious

The symbol table exposed a highly suspicious symbol:

### Command
```bash
nm -an ./catacombs | grep -Ei 'main|flag|bait|check|verify|input|secret'
```

### Key observation
A symbol named similar to:
```text
FLAG_BAIT_LABEL
```
was present.

### Why this matters
If the binary intentionally names a visible string as a bait label, then blindly submitting the string from `strings` is bad reversing hygiene.
I treated the visible `CIT{3R2rA2J0PdFH}` as **untrusted until I could make the binary print it through the actual success path**.

That turned out to be the right approach.

---

## 5. Reverse the command parser in `main`

Disassembling `main` shows the command loop and dispatch table.

### Command
```bash
objdump -d -Mintel ./catacombs --start-address=0x409723 --stop-address=0x409f20 | sed -n '1,260p'
```

### Relevant observations from `main`
`main`:
- prints the banner,
- reads a line with `getline`,
- parses the first token,
- compares against the command strings:
  - `help`
  - `status`
  - `hint`
  - `bait`
  - `notice-check`
  - `reset`
  - `step`
  - `script`
  - `submit`

In the disassembly, the `bait` branch directly references `FLAG_BAIT_LABEL`, which confirmed the deliberate decoy design.

I also saw that:
- `step` reads one syscall name and applies it,
- `script` reads multiple syscall tokens and forwards them to a helper,
- `submit` eventually reaches the hidden validation logic.

At this point I knew the interactive interface exactly, so I could stop guessing command syntax.

---

## 6. Recover syscall parsing

The helper `parseOpName` is straightforward and very useful.

### Command
```bash
objdump -d -Mintel ./catacombs --start-address=0x407ded --stop-address=0x407ee5
```

### Function behavior
`parseOpName`:
- lowercases the input,
- compares it against an array of 7 syscall names,
- returns the matching index,
- returns `-1` on failure.

### Recovered syscall alphabet
From strings and parser logic:
```text
0: openat
1: read
2: mmap
3: ioctl
4: futex
5: clone
6: close
```

This meant the challenge accepts only these seven symbolic operations.

---

## 7. Recover the visible state machine

The key visible logic is in the transition helpers.

### Important functions
- `resetRuntime` at `0x407ee6`
- `applyStepCore` at `0x407f32`
- `applyVisibleStep` at `0x40818e`
- `transcriptString` at `0x40827a`
- `runScript` at `0x408f24`
- `histogramOk` around `0x40880d`

### 7.1 `resetRuntime`
This initializes the runtime structure.

It sets the visible initial state printed by `status`:
- node = `0` (`mouth`)
- acc = `0xa17c39d4`
- breadcrumb = `0xc3b5da91`
- mix = `0x4d415a452d4c4142`
- cookie = `0xe1b9a7c33d55aa11`

This matched the live `status` output exactly, which is always a good consistency check.

### 7.2 `applyVisibleStep`

### Command
```bash
objdump -d -Mintel ./catacombs --start-address=0x40818e --stop-address=0x4081f1
```

### Observation
This function:
- reads the current node from global runtime `g_rt`,
- indexes into `EDGE_TABLE[current_node][op]`,
- gets the next node,
- calls `applyStepCore` with `(current_runtime, op, next_node)`.

This is the public transition system used when we type commands into the UI.

### 7.3 `applyStepCore`

This is the shared mixing routine.
It updates:
- current node,
- accumulator values,
- breadcrumbs/cookies,
- the trace array,
- step count.

Most of the body is arithmetic mixing and trace bookkeeping. The important reversing fact is:
- **it deterministically records the op sequence and resulting node sequence**,
- the validator can later reconstruct a second runtime from the same trace.

### 7.4 `transcriptString`
This helper converts the stored op indices back into a human-readable syscall sequence using `kSyscallNames`.
That confirmed the trace is literally an ordered list of the symbolic syscalls.

---

## 8. Recover the hidden validator idea

The most important discovery was that there are **two different edge systems**:

1. the **visible** one used during interactive stepping,
2. the **trusted** one used by validation.

### Commands
```bash
objdump -d -Mintel ./catacombs --start-address=0x4081f2 --stop-address=0x408279
```

### Relevant functions
- `trustedEdge` at `0x4081f2`
- `applyTrustedStep` at `0x408236`

### Observation
`trustedEdge(node, op)`:
- reads from `TRUSTED_PACKED_EDGES`, not `EDGE_TABLE`.

`applyTrustedStep(runtime, op)`:
- computes the next node using `trustedEdge`,
- then calls the same `applyStepCore`.

This explains the challenge structure:
- the visible machine lets us build some trace,
- the hidden validator likely **replays the trace through the trusted graph**,
- then checks whether the resulting trusted runtime reaches a blessed state.

That is why knowing only the syscall counts is insufficient.
The sequence order matters.

---

## 9. Recover the histogram constraint

The hint already leaked the operation counts, but I also confirmed that a dedicated histogram check exists in the binary.

### Observation
A helper near `0x40880d` performs a frequency check over the transcript.
Recovered required counts:

```text
openat = 2
read   = 2
mmap   = 1
ioctl  = 2
futex  = 1
clone  = 1
close  = 1
```

Total length = `10` steps.

### Implication
The search space is the set of distinct permutations of this multiset:

```text
10! / (2! * 2! * 2!) = 453600
```

That is small enough to brute force locally.

---

## 10. Extra hint analysis from the UI

The rotating hints gave more structure than just raw counts:

```text
chalk scrape: burial ledger from the ring buffer -> openat x2, read x2, mmap x1, ioctl x2, futex x1, clone x1, close x1
grave note: the sanctum only accepts close() when entered from sysproxy
field report: two openat calls bracket the fork path; futex is not the finale
```

### Observation
These clues strongly suggest:
- `close` must be the last step or near the end,
- the final predecessor before `close` must be `sysproxy`,
- `clone` sits somewhere between the two `openat` calls,
- `futex` is not last.

These hints make the brute force even easier, but I did not need to hand-solve the graph; brute force with the recovered transition logic was enough.

---

## 11. Solve by brute forcing the valid permutation

Once I understood:
- the allowed symbols,
- the required multiplicities,
- and that validation depends on order,

I brute-forced permutations of the multiset and fed each candidate to the binary using the proper interactive syntax.

### Recovered winning order
```text
openat, mmap, ioctl, read, futex, clone, openat, ioctl, read, close
```

In interactive form, the correct input is:

```text
script openat mmap ioctl read futex clone openat ioctl read close
submit
```

---

## 12. Verify the solve path through the binary

This is the critical step that proves the flag is real.

### Command
```bash
printf 'script openat mmap ioctl read futex clone openat ioctl read close
submit
' | timeout 3s ./catacombs
```

### Output
```text
[catacombs] syscall-lit ossuary trace harness
[catacombs] descend through the buried mesh and submit a coherent trace
type 'help' for commands
> hook openat -> node 3 (sepulcher)
hook mmap -> node 5 (cistern)
hook ioctl -> node 1 (ossuary)
hook read -> node 6 (lockdep)
hook futex -> node 2 (sysproxy)
hook clone -> node 4 (ringbuf)
hook openat -> node 1 (ossuary)
hook ioctl -> node 3 (sepulcher)
hook read -> node 2 (sysproxy)
hook close -> node 7 (sanctum)
> ACCESS GRANTED: CIT{3R2rA2J0PdFH}
```

### Final observation
Now the previously suspicious embedded string is confirmed as the **real flag**, because the binary itself prints it only after the valid trace is submitted.

So the flag is:

```text
CIT{3R2rA2J0PdFH}
```

---

## 13. Why the bait worked

This is a nice challenge design detail.

Early on, the binary leaks a literal `CIT{...}` through `strings`, which tempts players to stop immediately.
But:
- there is also a symbol named `FLAG_BAIT_LABEL`,
- the interactive command `bait` prints only a visible label (`flag`),
- the real solve requires reconstructing the valid syscall trace.

So the intended trap is:
1. see `CIT{...}` in `strings`,
2. submit it blindly,
3. miss the actual reversing component.

The correct workflow is to distrust the string until the program’s real success path reproduces it.

---

## 14. Summary of the reversing process

### Step-by-step summary
1. Checked file type: static, non-stripped ELF.
2. Ran `strings` and found both syscall names and a suspicious embedded flag string.
3. Ran the program and inspected `help`, `status`, `hint`, `bait`, `submit`.
4. Learned the interface is command-based with `step` / `script`.
5. Used symbols/disassembly to recover the parser and command dispatch.
6. Recovered syscall parser `parseOpName` and the 7 allowed operations.
7. Recovered visible transition logic via `EDGE_TABLE` and `applyVisibleStep`.
8. Recovered hidden validation concept via `trustedEdge` / `TRUSTED_PACKED_EDGES`.
9. Confirmed histogram constraint: `2,2,1,2,1,1,1` across the seven ops.
10. Brute-forced permutations of the 10-step multiset.
11. Found the unique working trace:
    - `openat mmap ioctl read futex clone openat ioctl read close`
12. Verified by feeding it to the binary and observing:
    - `ACCESS GRANTED: CIT{3R2rA2J0PdFH}`

---

## 15. Final answer

```text
CIT{3R2rA2J0PdFH}
```
