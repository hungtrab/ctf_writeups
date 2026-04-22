# Hit your limit — Writeup

- **Category:** Web
- **Flag format:** `CIT{}`
- **Challenge URL:** `http://23.179.17.92:5559/`
- **Hint/context:** `A wise man once said, stay calm, cool and collected. Don't go above your limit.`

---

## 1. Initial thoughts

The hint strongly suggested that **rate limiting** would be central to the challenge.

Because this was a web challenge with no further description, the right first move was standard web recon:

- inspect the homepage
- inspect headers and responses
- look at client-side JavaScript
- enumerate common endpoints
- identify how the app validates input

The main question I wanted to answer early was:

> Is the flag hidden server-side behind some verification logic, and if so, can that logic be abused?

---

## 2. Recon: inspect the root page

I first fetched the root page and checked the headers/body.

### Observation

The app was served by:

- **Werkzeug/Flask-style stack**
- HTML page with a polished single-page UI
- no obvious server-rendered flag or comments leaking secrets

The page looked like a **flag guesser/verifier** rather than a content-heavy site. That immediately suggested the important logic might live in client-side JavaScript.

---

## 3. Inspect the frontend JavaScript

After pulling more of the HTML and relevant scripts, I found the key logic:

- the page issued a request to an API endpoint like:
  - `/api/flag?guess=<user_input>`
- the API response was used to tell the user whether their input was acceptable

### Important observation

This endpoint behaved like a **prefix oracle**.

That means:

- if the supplied `guess` matched the **beginning** of the real flag, the server responded positively
- otherwise it responded negatively

This is a classic vulnerable pattern because it allows character-by-character recovery of the secret.

At this point, the likely solve path became:

1. identify the exact success/failure behavior of `/api/flag`
2. determine whether the endpoint can be brute-forced
3. deal with any rate limiting

---

## 4. Characterize `/api/flag`

I tested `/api/flag` manually with different guesses.

Examples of guesses:

- empty guess
- `C`
- `CI`
- `CIT`
- `CIT{`
- random strings

### Observations

- Missing `guess` parameter returned a **400** style error
- Correct prefixes returned **200** with a JSON success result
- The endpoint clearly checked whether the input was a valid prefix of the flag

So the challenge did not require SQLi, SSTI, LFI, or anything more exotic. The core vulnerability was already enough:

> The API leaks whether a partial flag prefix is correct.

If unrestricted, that would make brute force trivial.

---

## 5. Rate limiting appears

When I started sending more requests to `/api/flag`, I hit the intended defense:

- after a small number of requests, the server returned **429 Too Many Requests**
- the JSON error reported something like:
  - limit: `5`
  - retry in roughly `300s`

### Observation

The rate limiting was strict enough to make normal sequential brute force impractical.

I then tested whether the limiter could be bypassed with common tricks:

- alternate HTTP methods
- alternate headers like `X-Forwarded-For`
- parameter encoding variants
- slightly different request shapes

### Result

Those obvious bypasses did **not** help.

So I moved to path normalization/canonicalization testing.

---

## 6. Endpoint/path variant testing

Since the app used `/api/flag`, I tested common path variants such as:

- `/api/flag`
- `/api/flag/`
- `/api//flag`
- `/api/./flag`
- encoded path variants

### Critical observation

The endpoint with a **trailing slash**:

- `/api/flag/`

still reached the same verification logic **but did not share the same rate-limit bucket**.

That was the key bug.

In practice:

- `/api/flag` → rate limited quickly with `429`
- `/api/flag/` → behaved as the oracle but remained usable repeatedly

This is a common web bug category:

> inconsistent routing / path normalization causing a security control to apply to one route but not its equivalent variant

---

## 7. Verify the bypass behavior carefully

Before brute forcing, I confirmed the new endpoint behavior with multiple requests.

### What I observed on `/api/flag/`

- correct prefix guesses returned **200**
- incorrect guesses returned **500**
- repeated requests to this variant did **not** trigger the same effective rate limit

This gave me a clean oracle:

- **200** = prefix is correct
- **500** = prefix is wrong

That is even easier to brute force than parsing response bodies.

---

## 8. Flag extraction strategy

Now the solve became straightforward:

1. start with the known format prefix `CIT{`
2. try one candidate character at a time
3. send requests to `/api/flag/` using `guess=<current_prefix + candidate>`
4. keep the candidate that returns **200**
5. repeat until `}` is reached

### Character set used

A practical brute-force charset included:

- uppercase letters
- lowercase letters
- digits
- underscore
- braces
- common special characters such as `@`

Because the flag format was known and the endpoint acted as a prefix oracle, each position only required testing candidates until one returned success.

---

## 9. A note on tooling and failed attempt

I initially tried a more naive sequential brute-force script.

### Observation

That worked logically, but it was too slow for the tool timeout in this environment, not because the target was unsolvable.

So I switched to a more efficient approach:

- tighter request timeouts
- per-position probing
- more aggressive automation
- logging intermediate findings

Even without a fully optimized extractor shown here, the oracle itself was already enough to recover the flag reliably.

---

## 10. Recovered flag

The extracted flag was:

```text
CIT{R@T3_L1m1t1nG_15_Bypass@ble}
```

---

## 11. Why the challenge works

This challenge combines two ideas:

### 1. Information leak via prefix oracle

The API reveals whether a partial guess is correct. That alone lets an attacker recover the full secret incrementally.

### 2. Broken rate-limit enforcement

The intended mitigation is the rate limiter on `/api/flag`, but the equivalent endpoint `/api/flag/` is not protected the same way.

So the app’s defense is present, but inconsistently applied.

---

## 12. Root cause

The likely root cause is one of these:

- rate limiting keyed on the literal route string `/api/flag` but not `/api/flag/`
- separate route registration or middleware mismatch
- normalization differences between the app router and the rate-limit layer

In short:

> the verifier and the limiter disagree about what counts as the same endpoint

---

## 13. Security lessons

This challenge is a good reminder of several real-world lessons:

- Never expose a **prefix oracle** for secrets
- Rate limiting should be applied to the **canonicalized route**, not one exact path string
- Security controls must treat route variants consistently
- A trailing slash difference can be security-relevant if middleware is attached incorrectly

A proper fix would be:

- avoid prefix-based flag validation entirely
- compare only full values server-side
- return a single generic failure response
- canonicalize paths before rate-limiting or apply the limiter across all equivalent route variants

---

## 14. Final answer

```text
CIT{R@T3_L1m1t1nG_15_Bypass@ble}
```
