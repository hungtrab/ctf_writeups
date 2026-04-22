# Transmission from 1993 — Detailed Writeup

## Challenge Info
- **Name:** challenge
- **Category:** misc / forensics-style misc
- **Flag format:** `CIT{...}`
- **Final flag:** `CIT{fL3x_YOur_F4xiNG}`

---

## 1. Initial Recon

The challenge directory did **not** contain anything useful under `./files`, so the first observation was that the real artifact lived in the working directory itself.

Relevant artifact:
- `call-69e26052e9f5b0c1da0ee369.pcap`

Initial notes:
- The challenge title was **“Transmission from 1993”**.
- The description/noise hint strongly suggested old-school modem/fax signaling:
  - `REEEEEEE-KRRR-SKREEEEEE-BEEP BEEP BEEP`

That immediately pointed toward:
- modem traffic,
- fax-over-IP,
- audio/fax protocol extraction,
- or something encoded inside telecom signaling.

A quick `strings` pass on the PCAP gave the decisive protocol clue.

Example observation:
```bash
strings -a call-69e26052e9f5b0c1da0ee369.pcap | grep -Ei 't38|fax|modem|CIT\{'
```

Important output:
```text
m=image 34654 udptl t38
a=T38FaxVersion:0
a=T38MaxBitRate:9600
a=T38FaxRateManagement:transferredTCF
...
a=T38FaxUdpEC:t38UDPRedundancy
```

### Observation
This was not random noise or audio stego. It was **T.38 fax traffic carried over UDPTL**.

That changed the problem from “decode weird audio” into:
1. parse the T.38 exchange,
2. recover fax image data,
3. decode the page,
4. read the flag.

---

## 2. Why Straightforward Fax Replay Failed

The obvious next step was to try to replay the fax data through `spandsp` and let it reconstruct a TIFF automatically.

There were helper programs in the workspace already prepared for that direction:
- `t38_bidir_replay.c`
- `t38_rx_from_payloads.c`
- `dump_t30_meta.c`
- `dump_ecm_frames.c`

These were using `spandsp` APIs such as:
- `t38_terminal_*`
- `t30_*`
- `t38_core_rx_ifp_packet(...)`

### What `t38_bidir_replay.c` was doing
It re-fed bidirectional T.38 IFP payloads into a simulated sender/receiver and attempted to let `spandsp` recover received files:

```c
t30_set_rx_file(caller_t30, "caller_rx.tif", -1);
t30_set_rx_file(callee_t30, "callee_rx.tif", -1);
```

It also printed per-frame and phase-E statistics.

### Result
The transfer did not produce a clean finished TIFF page automatically. The statistics showed metadata, but not a successful final page reconstruction.

From `notes.md`:
```text
[caller-final] rx_ident='' rx_sender='' rx_sub='' rx_pwd='' country='Japan' vendor='Unknown - indeterminate' model='' pages_rx=0 width=0 length=0 encoding=0 image_size=0 bad_rows=0
[callee-final] rx_ident='+13136345403' rx_sender='' rx_sub='' rx_pwd='' country='' vendor='' model='' pages_rx=0 width=0 length=0 encoding=0 image_size=0 bad_rows=0
```

### Observation
The session metadata was being parsed, but the normal “just dump me the received fax image” route was not completing.

That meant I needed to inspect the **actual T.30/T.38 payload content** and recover the fax page manually.

---

## 3. Extracting T.30 / T.38 Information

The helper `dump_t30_meta.c` was important because it exposed transfer statistics from the T.30 layer.

Key line in the source:
```c
t30_get_transfer_statistics(t30, &st);
```

And it printed:
```c
fprintf(stderr,
  "[%s] ... encoding=%d image_size=%d ...\n",
  tag, ... st.encoding, st.image_size, ...);
```

From the solving notes, the decisive value was:
```text
encoding=4
```

### Critical Observation
This value corresponded to:
- **T.85 JBIG fax encoding**
- **not** Group 3 / Group 4 fax (MH/MR/MMR)

That explained why a bunch of standard fax-image assumptions were leading nowhere.

So the actual page payload was expected to be a **JBIG bitonal image stream**.

---

## 4. Extracting the ECM Page Chunks

The next useful helper was `dump_ecm_frames.c`.

Its real-time frame handler contained the key logic:

```c
if (strcmp(st->name,"callee")==0 && direction==1 && len==260 &&
    msg[0]==0xff && msg[1]==0x03 && msg[2]==0x06) {
    fprintf(ecm_out, "%02x", msg[3]);
    for (int i=4;i<len;i++) fprintf(ecm_out, "%02x", msg[i]);
    fprintf(ecm_out, "\n");
}
```

### What that means
This handler was watching T.30 real-time frames and selecting ECM data blocks matching the expected structure. It then dumped them as hex lines into:
- `ecm_frames_hex.txt`

The resulting file contained **8 ECM frame lines**.

Evidence:
```text
wc -l ecm_frames_hex.txt
8 ecm_frames_hex.txt
```

The first bytes of the first dumped block looked like this:
```text
0000000100000006c00000086c000000807f000028324b58...
```

### Important Observation
Those initial bytes were highly suggestive of a manually reconstructable image payload:
- width-like values,
- height-like values,
- BIH/header-like structure,
- followed by compressed data.

Eventually, the reconstructed payload was written to:
- `ecm_page_payload.bin`

File size:
```text
ecm_page_payload.bin 2048 bytes
```

---

## 5. First Wrong Path: Treating It Like Traditional Fax (MMR/G3/G4)

Because fax challenges often boil down to Group 3 or Group 4 image data, I tried variants that interpreted the page as conventional fax compression.

Artifacts left from that experimentation include:
- `ecm_mmr_h1000.tif`
- `ecm_mmr_h800.tif`
- `ecm_mmr_h600.tif`
- `ecm_mmr_h500.tif`
- `ecm_mmr_h400.tif`
- `ecm_mmr_h300.tif`
- `ecm_mmr_h250.tif`
- `ecm_mmr_h200.tif`
- `ecm_mmr_h150.tif`
- `ecm_mmr_h100.tif`
- corresponding `.png` conversions

These are classic signs of trying:
- different image heights,
- different line counts,
- TIFF wrappers around suspected MMR data.

### Observation
Those attempts were dead ends because the transmission was **not MMR/G4 at all**. The T.30 metadata was the important correction: **use JBIG, not Group 3/4**.

This is a very common pitfall in fax problems.

---

## 6. Reconstructing a JBIG Stream

Once the page was recognized as JBIG, the strategy shifted to building a valid `.jbg` file and testing it with a JBIG decoder.

There were a number of candidate reconstruction variants generated during trial-and-error, such as:
- `jbg_try_none_orig.jbg`
- `jbg_try_none_strip_both.jbg`
- `jbg_try_none_strip_ff00_to_ff.jbg`
- `jbg_try_none_strip_ff02_to_ff.jbg`
- `jbg_try_sdnorm_orig.jbg`
- `jbg_try_esc_sdnorm_orig.jbg`
- `jbg_try_esc_rst_orig.jbg`
- and corresponding `rstrip0` variants

These names reflect multiple hypotheses about how the ECM/JBIG framing should be normalized:
- keep the payload as-is,
- rewrite escape sequences,
- convert `ff00` → `ff`,
- convert `ff02` → `ff`,
- strip framing markers,
- trim padding.

### The successful candidate
The one that ultimately decoded was:
- `jbg_try_none_rstrip0.jbg`

File size:
```text
jbg_try_none_rstrip0.jbg 1996 bytes
```

---

## 7. Using `jbgtopbm -d` to Read the Decoder’s Clues

The **most important diagnostic step** was running the JBIG decoder in diagnostic mode.

Command:
```bash
jbgtopbm -d jbg_try_none_rstrip0.jbg
```

Important output:
```text
BIH:

  DL = 0
  D  = 0
  P  = 1
  XD = 1728
  YD = 2156
  L0 = 128
  MX = 127
  MY = 0
  options = 40  VLENGTH TPBON

  17 stripes, 1 layers, 1 planes => 17 SDEs
```

Then the decoder enumerated all stripe data entities:
```text
00012c: ESC SDNORM, ending SDE #1
00013c: ESC SDNORM, ending SDE #2
...
0007ca: ESC SDNORM, ending SDE #17 (final SDE)
```

### Critical Observation
This told me:
1. The stream structure was fundamentally valid.
2. The BIH parameters were sane.
3. The decoder could parse the data all the way to the **final SDE**.
4. The remaining issue was **extra junk after the real end of the stream**.

That junk turned out to be **trailing null padding**.

This was the turning point of the solve.

---

## 8. The Final Bug: Trailing Zero Padding

The ECM reconstruction produced a page-sized binary blob of 2048 bytes, but the real JBIG stream ended earlier.

Evidence from file sizes:
```text
ecm_page_payload.bin 2048 bytes
jbg_try_none_rstrip0.jbg 1996 bytes
```

That 52-byte difference was not meaningful image data — it was null padding after the final SDE.

### Why this matters
A decoder may accept the internal syntax up to the final stripe but still fail or behave oddly if the payload includes extra bytes after the logical end of image data.

By stripping the trailing `0x00` bytes after the final SDE, the reconstructed stream became a valid decodable JBIG file.

From `notes.md`:
```text
[*] jbgtopbm -d showed valid JBIG stream with extra trailing zero padding after final SDE
[*] Stripping trailing zeros allowed successful decode to PBM
```

This was exactly the hidden issue.

---

## 9. Successful Decode to Image

After trimming the trailing padding, the decoder produced a PBM image successfully.

Recovered files:
- `jbg_try_none_rstrip0.jbg`
- `jbg_try_none_rstrip0.jbg.pbm`
- `jbg_try_none_rstrip0.jbg.png`

File info:
```text
jbg_try_none_rstrip0.jbg.pbm: , rawbits, bitmap
jbg_try_none_rstrip0.jbg.png: PNG image data, 1728 x 2156, 1-bit grayscale, non-interlaced
```

The PBM header confirms the final page dimensions:
```text
P4
1728
2156
```

Hex dump of the header:
```text
00000000: 50 34 0a ... 31 37 32 38 0a ... 32 31 35 36 0a
```

### Observation
Those dimensions are perfectly consistent with a fax page raster.

At this point, opening the rendered image revealed the text of the flag.

---

## 10. Flag

Visible on the decoded fax page:

```text
CIT{fL3x_YOur_F4xiNG}
```

So the final answer is:

```text
CIT{fL3x_YOur_F4xiNG}
```

---

## 11. Short Solve Path Summary

If I compress the entire solve into the minimal set of meaningful steps, it is:

1. Inspect the challenge files.
2. Notice the real artifact is a PCAP, not something in `./files`.
3. Run `strings` on the PCAP and identify **T.38 fax over UDPTL**.
4. Replay / parse T.30 metadata.
5. Observe `encoding=4`, meaning **T.85 JBIG**.
6. Extract ECM blocks into hex and reconstruct the page payload.
7. Build candidate JBIG streams from the payload.
8. Use `jbgtopbm -d` diagnostics to confirm the stream is valid **up to the final SDE**.
9. Strip the trailing null padding after the final SDE.
10. Decode the cleaned JBIG to PBM/PNG.
11. Read the flag from the recovered page image.

---

## 12. Key Lessons / Observations

### A. Fax challenge != always Group 3/4
The biggest trap here was assuming the image data should be decoded as ordinary fax MMR/G3/G4. The actual encoding was **JBIG**, which is much less common in CTFs.

### B. Decoder diagnostics matter
The `jbgtopbm -d` output was not just noise — it explicitly revealed that the stream was structurally valid and that the issue was at the tail end.

### C. Padding can break otherwise-valid reconstructions
When carving a payload out of network framing/ECM transport blocks, the transport-layer size may exceed the logical end of the actual encoded object. Trailing padding bytes can be enough to derail a decoder.

### D. T.30 metadata is extremely useful
The single field `encoding=4` saved a lot of wasted time.

---

## 13. Files of Interest

Primary challenge artifact:
- `call-69e26052e9f5b0c1da0ee369.pcap`

Useful extracted/intermediate files:
- `t38_bidir_payloads.txt`
- `t38_sender_payloads.txt`
- `ecm_frames_hex.txt`
- `ecm_page_payload.bin`

Helper programs / source:
- `t38_bidir_replay.c`
- `dump_t30_meta.c`
- `dump_ecm_frames.c`
- `t38_rx_from_payloads.c`

Final successful decode artifacts:
- `jbg_try_none_rstrip0.jbg`
- `jbg_try_none_rstrip0.jbg.pbm`
- `jbg_try_none_rstrip0.jbg.png`

Notes:
- `notes.md`

---

## 14. Final Answer

```text
CIT{fL3x_YOur_F4xiNG}
```
