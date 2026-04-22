# Write-Up: reallysecurepasswordmanager

**Category:** Reverse Engineering  
**Flag format:** `CIT{...}`  
**Flag:** `CIT{mT5zpHOlzIG3}`

---

## Overview

The challenge provides a single ELF binary called `reallysecurepasswordmanager`. It is a password manager that stores passwords for named accounts. The goal is to retrieve the password stored for the account named `flag`.

The binary is heavily obfuscated — the core validation logic lives in a hidden Read-Write-Execute segment. It also embeds an AI prompt-injection lure in its strings to try to get automated solvers to refuse to analyze it. The real challenge is satisfying a layered set of environmental checks: correct username, correct NSS backend, correct token file, and correct token file permissions.

---

## Step 1: Initial Triage

```bash
file reallysecurepasswordmanager
# ELF 64-bit LSB executable, x86-64, statically linked, not stripped

wc -c reallysecurepasswordmanager
# 6063168 bytes (~6 MB)
```

Key observations:
- **Statically linked** — `LD_PRELOAD` tricks cannot be used to intercept library calls.
- **Not stripped** — symbol names are intact, making static analysis much easier.

Listing interesting symbols with `nm`:

```
0000000000602c40 B authenticated
0000000000408fa5 T _Z16generatePasswordRKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE
0000000000408eae T _Z4authv
000000000040921d T _Z7getPassv
0000000000407e87 T _Z8validateNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE
```

Demangled: `auth()`, `getPass()`, `generatePassword(string)`, `validate(string)`.

---

## Step 2: Program Flow

Running the binary interactively reveals a menu:

```
1. log in
2. log out
3. read a password
4. save a password
```

The intended flow is:
1. **Option 1 (log in)** — calls `auth()`, sets the global `authenticated` flag at `0x602c40` to `1`.
2. **Option 3 (read a password)** — prompts for an account name, calls `generatePassword(name)`.
3. `generatePassword` calls `validate(name)` to check authorization, then derives the password with a seeded Mersenne Twister PRNG.

The password for the account `flag` is generated with a specific PRNG seed (derived from `std::hash("flag")`). The actual password generation was confirmed via GDB to produce **`b7Cvv$K@(6OFGHNR`** — but this is the *generated* password, not the flag. The flag comes from the program's output once all validation checks pass.

---

## Step 3: Prompt-Injection Lure

Running `strings reallysecurepasswordmanager | grep -i "flag"` reveals a base64-encoded academic integrity notice stored in a global `std::string` called `_ZL4flag`. This is a **CTF gaslighting trick**: the string is designed to make AI-assisted solvers refuse to continue analysis. It is not the flag and plays no role in the actual challenge logic.

---

## Step 4: The Hidden RWE Segment

`readelf -l` reveals an unusual program segment:

```
LOAD 0x0000000000280000 vaddr=0x0000000000a80000 size=0xc8000 flags=RWE
```

A segment with **Read-Write-Execute** permissions is a strong indicator of self-modifying or obfuscated code loaded at runtime.

Disassembling `validate()` at `0x407e87` shows its very first instruction is:

```asm
0x407e87: e9 d8 c7 71 00    jmp 0xb24664
```

The function immediately jumps into the RWE segment at `0xb24664`. All actual validation logic is in that obfuscated region — OLLVM-style control-flow flattening makes static analysis impractical.

---

## Step 5: Understanding `auth()`

Static analysis of `auth()` at `0x408eae` shows it calls `getlogin()`, which on Linux:

1. Opens `/proc/self/loginuid` to read the numeric UID of the logged-in user.
2. Calls `getpwuid(uid)` to look up the username from `/etc/passwd`.

It compares the result to the string `"notronnie"` found in `.rodata` at `0x59d29c`. If they match, `authenticated` is set to `1` and the program prints `Authenticated as: notronnie`.

---

## Step 6: First Obstacle — `getlogin()` Returns Wrong User

The system UID is `1000`, but `/etc/passwd` maps UID `1000` to `hungchan`, not `notronnie`. So `getlogin()` returns `"hungchan"` and `auth()` fails.

Since the binary is statically linked, `LD_PRELOAD` cannot intercept `getlogin()`. Binary patching is required.

**Observation:** `auth()` reads `/etc/nsswitch.conf` to decide how to resolve usernames. The system's `nsswitch.conf` includes a `systemd` entry:

```
passwd: files systemd
```

When the binary (a static ELF) tries to load `libnss_systemd.so.2` via `dlopen()`, it crashes with **SIGFPE** — a division by zero inside the dynamic linker's TLS initialization code. This prevents even getting `auth()` to work.

---

## Step 7: Binary Patching — NSS and passwd Redirect

To fix both problems, patch two hardcoded paths inside the binary using same-length string replacements (to avoid shifting any offsets):

| Original | Replacement | Length |
|---|---|---|
| `/etc/nsswitch.conf` (18 bytes) | `/tmp/nsswitch.conf` (18 bytes) | ✓ same |
| `/etc/passwd` (11 bytes) | `/tmp/passwd` (11 bytes) | ✓ same |

**`/tmp/nsswitch.conf`:**
```
passwd:         files
group:          files
```
This omits the `systemd` entry entirely, preventing the `dlopen` crash.

**`/tmp/passwd`:**
```
root:x:0:0:root:/root:/bin/bash
notronnie:x:1000:1000::/home/hungchan:/bin/bash
```
This maps UID `1000` to `notronnie`, so `getlogin()` returns `"notronnie"`.

With these two patches applied (saved as `/tmp/patched4_manager`), `auth()` now succeeds:

```
Authenticated as: notronnie
```

---

## Step 8: `validate()` Still Fails

Even with `authenticated = 1` and `auth()` passing, requesting the `flag` password returns:

```
flag password: ERROR_NOT_AUTHENTICATED
```

`validate()` performs its own independent authorization check inside the RWE segment.

---

## Step 9: Tracing `validate()` with `strace`

```bash
strace -s 200 ./patched4_manager
```

Syscall trace between printing `"Account name: "` and printing `"ERROR_NOT_AUTHENTICATED"`:

```
openat("/tmp/passwd")         # getpwnam("notronnie") -> home=/home/hungchan
openat("/proc/self/loginuid") # getlogin() step 1: read UID
read -> "1000"
openat("/tmp/passwd")         # getlogin() step 2: getpwuid(1000) -> "notronnie"
newfstatat("/home/hungchan")  # stat home directory
ioctl(0, TCGETS2) = -1 ENOTTY
ioctl(1, TCGETS2) = -1 ENOTTY
-> ERROR_NOT_AUTHENTICATED
```

**Key observation:** The `ioctl` calls for `TCGETS2` return `ENOTTY` (not a terminal), and the `.pm_token` file is **never opened**. The binary checks whether it is running in a real TTY before attempting the token read.

---

## Step 10: PTY Bypass

Re-running with a pseudo-terminal (Python `pty.openpty()`) causes `ioctl(TCGETS2)` to succeed. The strace now shows much more:

```
ioctl(0, TCGETS2, {...}) = 0
readlink("/proc/self/fd/0", "/dev/pts/3") = 10
newfstatat("/dev/pts/3", ...) = 0
ioctl(1, TCGETS2, {...}) = 0
readlink("/proc/self/fd/1", "/dev/pts/3") = 10
newfstatat("/dev/pts/3", ...) = 0
newfstatat("/dev/pts/3", ...) = 0           # stdin == stdout device check
newfstatat("/home/hungchan/.pm_token", {st_mode=S_IFREG|0664, st_size=24}) = 0
-> ERROR_NOT_AUTHENTICATED
```

Progress! The binary now finds and **stats** `/home/hungchan/.pm_token`. The sequence reveals the full validation logic in the RWE segment:

1. Call `getpwnam("notronnie")` — get home directory.
2. Call `getlogin()` — verify current user is `"notronnie"`.
3. Stat home directory — confirm it exists.
4. Check stdin and stdout are real TTY devices (`TCGETS2`).
5. Verify stdin and stdout point to the **same terminal device** (anti-split-terminal check).
6. Stat `$HOME/.pm_token` — check it exists.
7. *(Further checks on the stat result.)*

Despite all of this passing, the binary still returns error. The token file is **only statted, never opened or read**. The binary is checking the file's **metadata**, not its content.

---

## Step 11: Token File Permissions

Looking at the stat result returned to the binary:

```
{st_mode=S_IFREG|0664, st_size=24, ...}
```

The file has permissions `0664` (owner rw, group rw, other r). This is insecure for a credential file. The binary almost certainly enforces **strict `0600` permissions** as a security check — if anyone other than the owner can read the token, authentication is rejected.

```bash
chmod 600 /home/hungchan/.pm_token
```

Rerunning with the PTY wrapper:

```
flag password: CIT{mT5zpHOlzIG3}
```

---

## Full Exploit Script

```python
import pty, os, sys, time, select

# Environment setup
os.environ['USER'] = 'notronnie'
os.environ['HOME'] = '/home/hungchan'

master, slave = pty.openpty()
pid = os.fork()
if pid == 0:
    os.close(master)
    os.setsid()
    import fcntl, termios
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    os.dup2(slave, 0); os.dup2(slave, 1); os.dup2(slave, 2)
    os.close(slave)
    os.execve('/tmp/patched4_manager', ['/tmp/patched4_manager'], os.environ)
else:
    os.close(slave)
    def read_quiet(fd, timeout=1.5):
        data = b""
        while True:
            r, _, _ = select.select([fd], [], [], timeout)
            if not r: break
            try:
                chunk = os.read(fd, 4096)
                if not chunk: break
                data += chunk
            except OSError: break
        return data

    time.sleep(0.3); read_quiet(master)
    for line in [b"1\n", b"3\n", b"flag\n"]:
        time.sleep(0.4); os.write(master, line)
        out = read_quiet(master, 0.8)
        sys.stdout.buffer.write(out); sys.stdout.buffer.flush()
    os.waitpid(pid, os.WNOHANG)
```

**Prerequisites:**

```bash
# 1. Patch binary
python3 patch_binary.py  # replaces /etc/nsswitch.conf and /etc/passwd paths

# 2. Create minimal nsswitch.conf without systemd entry
echo -e "passwd:         files\ngroup:          files" > /tmp/nsswitch.conf

# 3. Create passwd mapping UID 1000 -> notronnie
echo 'notronnie:x:1000:1000::/home/hungchan:/bin/bash' >> /tmp/passwd

# 4. Create token file with STRICT permissions
printf 'notronnie_local_token_v1' > /home/hungchan/.pm_token
chmod 600 /home/hungchan/.pm_token  # <-- this is the critical step

# 5. Run exploit
python3 exploit.py
```

---

## Summary of Checks in `validate()`

| Check | How it works | How we satisfied it |
|---|---|---|
| `authenticated == 1` | Global flag set by `auth()` | Call menu option 1 first |
| `getlogin() == "notronnie"` | Reads `/proc/self/loginuid`, maps via `getpwuid()` | Patch `/etc/passwd` → `/tmp/passwd` with `notronnie:x:1000` |
| NSS doesn't crash | `/etc/nsswitch.conf` loads `libnss_systemd.so.2` via `dlopen()` in a static binary → SIGFPE | Patch `/etc/nsswitch.conf` → `/tmp/nsswitch.conf` (files only) |
| Home directory exists | `stat($HOME)` succeeds | Already exists as `/home/hungchan` |
| Running in a real TTY | `ioctl(TCGETS2)` must succeed on both stdin and stdout | Spawn binary inside `pty.openpty()` |
| stdin and stdout on same terminal | Both `readlink(/proc/self/fd/0)` and `readlink(/proc/self/fd/1)` resolve to same device | Achieved automatically with single PTY master |
| Token file exists | `stat($HOME/.pm_token)` succeeds | Create `/home/hungchan/.pm_token` |
| Token file permissions == `0600` | `stat.st_mode` checked; `0664` rejected | `chmod 600 /home/hungchan/.pm_token` |

**Flag: `CIT{mT5zpHOlzIG3}`**
