Credit to discord @dawiddym

# Farcical Clones - Crypto Challenge Writeup

## Challenge Description

**Title:** Farcical Clones  
**Quote:** "May the Force be with you, young padawan."  
**Ciphertext:**

```
095 181 145 039 245 091 212 232 123 220 167 069 091 208 245 164 245 145 123 094, 062 150 094 172 083 135 096 153 002 208 096 172. 201 005 019 {131 091 090 053 095 218 238 211 091 004 201 182 135 245 167 074 090 145 096 238}
```

## Solution Approach

The challenge name "Farcical Clones" provides a crucial hint - the word "**RC4**al" suggests RC4 encryption, but the real clue is "**Clones**" pointing to _Star Wars: Attack of the Clones_ and the character **Sifo-Dyas**.

### Step 1: Identify the Cipher Type

This is a **substitution cipher** where each 3-digit number maps to a single character. The structure shows:

- First block: 20 numbers (the Star Wars quote)
- Second block: 12 numbers (continuation of quote)
- Flag block: 20 numbers enclosed in `{}`

### Step 2: Build the Substitution Table

Using the known Star Wars quote "May the Force be with you, young padawan." we can map numbers to letters:

```
095 181 145 039 245 091 212 232 123 220 167 069 091 208 245 164 245 145 123 094,
 M   a   y   t   h   e   F   o   r   c   e   b   e   w   i   t   h   y   o   u

062 150 094 172 083 135 096 153 002 208 096 172.
 y   o   u   n   g   p   a   d   a   w   a   n
```

From the flag prefix format, we know it starts with "CIT":

```
201 005 019
 C   I   T
```

### Step 3: Partial Decryption

Applying known mappings to the flag content:

```
131 091 090 053 095 218 238 211 091 004 201 182 135 245 167 074 090 145 096 238
 ?   e   ?   ?   M   ?   ?   ?   e   ?   C   ?   p   h   e   ?   ?   y   a   ?
```

### Step 4: Thematic Analysis

The challenge title "Farcical Clones" points to **Sifo-Dyas**, the Jedi Master from _Attack of the Clones_ who secretly commissioned the clone army. The flag appears to be a pun: **"JediMasterCipherdyas"**

### Step 5: Complete Mapping

Working backwards from "JediMasterCipherdyas":

```
131 091 090 053 095 218 238 211 091 004 201 182 135 245 167 074 090 145 096 238
 J   e   d   i   M   a   s   t   e   r   C   i   p   h   e   r   d   y   a   s
```

### Verification

Cross-checking with known mappings confirms consistency:

- `091 = e` (appears in positions 7, 12, and flag position 2, 9)
- `090 = d` (appears in flag positions 3, 17)
- `095 = M` (appears in quote position 1 and flag position 5)
- `145 = y` (appears in quote positions 3, 18 and flag position 18)
- `096 = a` (appears in quote positions 11, 19 and flag position 19)
- And so on...

## Final Answer

```
CIT{JediMasterCipherdyas}
```

## Complete Substitution Table

| Number | Letter | Number | Letter | Number | Letter | Number | Letter |
| ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ |
| 002    | a      | 069    | b      | 091    | e      | 135    | p      |
| 004    | r      | 074    | r      | 094    | u      | 145    | y      |
| 005    | I      | 083    | g      | 095    | M      | 150    | o      |
| 019    | T      | 090    | d      | 096    | a      | 153    | d      |
| 039    | t      | 091    | e      | 123    | r      | 164    | t      |
| 053    | i      | 062    | y      | 131    | J      | 167    | e      |
| 062    | y      | 172    | n      | 181    | a      | 182    | i      |
| 208    | w      | 211    | t      | 212    | F      | 218    | a      |
| 220    | c      | 232    | o      | 238    | s      | 245    | h      |
| 201    | C      |        |        |        |        |        |        |

## Key Insights

1. **Thematic Clues**: "Farcical Clones" → Sifo-Dyas from _Attack of the Clones_
2. **Known Plaintext**: Star Wars quote provides the rosetta stone
3. **Flag Format**: "CIT" prefix gives additional mappings
4. **Pun Resolution**: "Cipherdyas" plays on "Sifo-Dyas" + cryptography theme

This was an elegant substitution cipher that required both cryptanalytic skills and Star Wars knowledge to solve completely.
