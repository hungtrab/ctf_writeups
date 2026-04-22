# challenge — Writeup

## Challenge info
- **Name:** challenge
- **Category:** misc
- **Flag format:** `CIT{}`
- **Given files / hints:**
  - `desc.txt`
  - `cc.py`
- **Remote target:** `23.179.17.92:5670`

## Final flag
`CIT{my_0th3r_c4r_1s_a_c4n_bus}`

---

## 1. Initial inspection

The challenge description was minimal:

```text
Your Car Called

something about check engine lights

23.179.17.92:5670
```

That immediately suggested an **automotive / OBD-II / CAN bus** themed challenge.

I also checked the provided script `cc.py`. Its contents were very important because they showed exactly how the service was meant to be spoken to.

### Key observations from `cc.py`
- It connects to `23.179.17.92:5670` over **TCP**.
- It waits for an **ELM327** style banner.
- It sends commands terminated by `\r`.
- The example commands are OBD-II requests such as:
  - `010C` → engine RPM
  - `010D` → speed
  - `0105` → coolant temperature
  - etc.

So the service was acting like an **ELM327 adapter emulator**, which usually sits in front of an OBD-II / CAN interface.

That established the intended protocol family:
- ELM327 AT commands
- OBD-II service requests
- potentially raw CAN / UDS style requests behind the adapter

---

## 2. Talking to the service

The first step was to verify the protocol and see how “real” the emulator was.

Typical setup commands for an ELM327 session are:

```text
ATI
ATE0
ATL0
ATS0
ATH1
ATSP0
```

### Why these matter
- `ATI` identifies the adapter
- `ATE0` disables echo
- `ATL0` disables linefeeds
- `ATS0` disables spaces
- `ATH1` enables CAN headers in responses
- `ATSP0` sets protocol to automatic

### Observed behavior
The service responded like a normal emulator:
- `ATI` returned something equivalent to **ELM327 v1.5**
- protocol identified as **ISO 15765-4 CAN (11-bit, 500 kbaud)**

This confirmed the target was indeed pretending to be a car diagnostic interface.

---

## 3. Standard OBD-II enumeration

Per the challenge notes and the hint in the prompt, the first thing to do was enumerate standard OBD-II data.

### Commands used
Examples included:

```text
0100
0105
010C
010D
0111
03
04
0902
```

### What each does
- `0100` → supported PID bitmap
- `0105` → coolant temperature
- `010C` → engine RPM
- `010D` → vehicle speed
- `0111` → throttle position
- `03` → read diagnostic trouble codes (DTCs)
- `04` → clear diagnostic trouble codes
- `0902` → VIN

### Observations
The box behaved like a simulated car ECU and returned believable values:
- coolant temperature around `0x5C` → 52°C after the standard OBD conversion
- RPM bytes `1B20` → 1736 RPM
- speed `0x52` → 82 km/h
- throttle around `0x4D` → roughly 30%
- VIN query returned:
  - `1HGCM82633A004352`

It also returned DTC-related data. Clearing DTCs with mode `04` appeared to succeed.

### Important conclusion
At this stage, I had confirmed:
1. the service was not random text; it genuinely implemented OBD-style responses
2. but **nothing in the standard OBD-II PIDs directly exposed the flag**

That meant the challenge likely required going **beyond stock OBD PIDs**.

---

## 4. Testing whether the simulator was stateful

Because the prompt referenced check-engine-light style behavior, a natural hypothesis was:
- maybe the simulator has an internal “broken car” state
- maybe clearing DTCs or changing ECU state causes it to reveal the flag

So I tested the system before and after control-style operations such as reading and clearing faults.

### Observation
The clear-DTC path looked mostly like **fake cosmetic state**. It returned plausible responses, but there was no meaningful state change that led to a flag.

This was the turning point: it suggested the intended solve was **not** “repair the car with basic OBD commands.”

---

## 5. Header and ECU probing

A common next step with ELM327/CAN challenges is to see whether multiple ECU IDs respond.

I tested various request headers around the standard functional and physical addressing range, such as:
- `7DF`
- `7E0`–`7E7`
- nearby values

and then re-issued standard requests.

### Observation
The system mostly behaved like a **single canned ECU**, with replies from a normal-looking engine ECU response ID such as `7E8`.

That meant there was probably not a huge hidden network of ECUs to brute force through ordinary Mode 01 requests.

---

## 6. Key insight: try UDS-style services through the ELM327

At this point, the standard OBD path looked exhausted.

A very common CTF trick with CAN/OBD simulators is:
- standard OBD is there as a theme / decoy
- the real data is hidden behind **UDS (Unified Diagnostic Services)**
- the ELM327 is simply passing raw CAN payloads once the proper header is set

So instead of sending requests like `010C`, I started trying **raw diagnostic services** after selecting a target ECU header.

The most promising service here was:
- **UDS service `0x22`** = `ReadDataByIdentifier`

That service reads a manufacturer- or ECU-specific data identifier (DID).

---

## 7. The winning request

The successful sequence was:

```text
ATSH 7E0
22F1A5
```

### What this means
- `ATSH 7E0`
  - set the transmit CAN header to `0x7E0`
  - `7E0` is the conventional engine ECU request ID in 11-bit CAN diagnostics
- `22F1A5`
  - send UDS service `0x22` (ReadDataByIdentifier)
  - request identifier `F1A5`

This is not a normal public OBD-II PID. It is a **custom diagnostic identifier**.

---

## 8. Response analysis

The ECU responded over multiple frames:

```text
7E8 0: 62F1A54349547B
7E8 1: 6D795F30746833
7E8 2: 725F6334725F31
7E8 3: 735F615F63346E
7E8 4: 5F6275737D
```

### Why this is clearly correct
- The reply ID `7E8` is the normal ECU response counterpart to request ID `7E0`
- UDS positive response to service `0x22` is `0x62`
- The response starts with:

```text
62 F1 A5 ...
```

That means:
- positive response to ReadDataByIdentifier
- data for DID `F1A5`

The remainder is payload data.

---

## 9. Decoding the payload

Remove the `62F1A5` prefix from the first frame, then concatenate the remaining hex data from all frames:

```text
4349547B
6D795F30746833
725F6334725F31
735F615F63346E
5F6275737D
```

Concatenated:

```text
4349547B6D795F30746833725F6334725F31735F615F63346E5F6275737D
```

Hex-decoding that gives:

```text
CIT{my_0th3r_c4r_1s_a_c4n_bus}
```

This matches the required flag format exactly.

---

## 10. Why this was the intended solve

Several facts line up neatly:

1. The provided script explicitly centered the challenge on the automotive diagnostic interface.
2. The target port `5670` itself was enough to solve the challenge.
3. Standard PIDs worked, but only as world-building / realism.
4. The actual flag was hidden behind a **custom UDS DID**, which is a very natural escalation from basic OBD-II to deeper diagnostics.
5. The flag text itself references **CAN bus**, reinforcing that the intended theme was in-band vehicle diagnostics, not some unrelated side service.

---

## 11. Dead-end / misleading avenue encountered

During exploration, there were observations about other ports on the same IP and even unrelated web behaviors. Those did produce interesting artifacts, but they were not the intended path for this challenge.

The decisive clue was the user observation that port `5670` was likely “just a simulator, so it can be controlled.” That pushed the analysis back onto the actual automotive interface, which led directly to the UDS solution.

In hindsight, that was the correct framing:
- **do not pivot away too early**
- treat the OBD emulator as a controllable diagnostic endpoint
- try raw UDS services, not only standard OBD modes

---

## 12. Minimal solve steps

If I had to summarize the solve in the shortest reproducible form:

1. Connect to `23.179.17.92:5670`
2. Initialize the ELM327 interface
3. Set the header to engine ECU `7E0`
4. Send a custom UDS ReadDataByIdentifier request
5. Decode the multi-frame hex payload as ASCII

Example session:

```text
ATI
ATE0
ATL0
ATS0
ATH1
ATSH 7E0
22F1A5
```

Response:

```text
7E8 0: 62F1A54349547B
7E8 1: 6D795F30746833
7E8 2: 725F6334725F31
7E8 3: 735F615F63346E
7E8 4: 5F6275737D
```

Decode to:

```text
CIT{my_0th3r_c4r_1s_a_c4n_bus}
```

---

## 13. Lessons / takeaways

- When a service emulates **ELM327**, don’t stop at stock OBD-II PIDs.
- If ordinary telemetry looks realistic but unhelpful, switch to **UDS services**.
- `0x22` / `ReadDataByIdentifier` is a high-value service to probe in ECU-themed CTF challenges.
- Multi-frame CAN/UDS responses often hide printable ASCII or a flag split across hex chunks.
- Challenge realism can be used as misdirection: a believable ECU simulator may still hide the secret in a custom DID rather than any public automotive field.

---

## Flag
`CIT{my_0th3r_c4r_1s_a_c4n_bus}`
