# Writeup - challenge (misc)

## Challenge info

- **Name:** challenge
- **Category:** misc
- **Flag format:** `CIT{}`
- **Description:**

  ```
  ASCII and Ye Shall Receive

  Please Hold While Your Packet Is Being Routed Through Different Protocols From Different Decades And One Of Them Requires You To Read A Manual From 1986

  23.179.17.92:2323
  ```

## Final flag

```text
CIT{Acc355_C0ntr0l_M@tt3rs!}
```

---

## High-level overview

This challenge was a multi-hop misc challenge built around moving through several services and protocols:

1. Start from a **BBS-like service** on port `2323`
2. Discover that the host exposes additional services
3. Find a **web page on port 8080** leaking an **OpenSSH private key**
4. Use that key to access a **custom SSH service on port 2222**
5. Observe that the SSH service is not a shell but a **restricted HTTP-like jail**
6. Explore other exposed web apps
7. Find that the app on **port 5001** has an **authenticated IDOR** on report IDs
8. Enumerate report IDs until one reveals the flag

The important lesson was exactly what the final flag says: **access control matters**.

---

## Step 1 - Initial local triage

The workspace did not contain any real challenge files inside `./files`, so the first useful artifact was the challenge description itself.

### Observation

- `./files` was effectively empty
- The description mentioned a live target: `23.179.17.92:2323`
- The phrase **“Different Protocols From Different Decades”** strongly suggested the challenge would require hopping across multiple network services rather than solving a static file
- The phrase **“read a manual from 1986”** hinted at an older protocol or HTTP-era behavior

At this point, the correct move was to interact with the remote host rather than spend time on local files.

---

## Step 2 - Connect to port 2323

Port `2323` commonly suggests telnet-like services, BBS systems, MUDs, or custom text interfaces.

A basic probe with `nc` showed that the service was interactive and rendered a retro text UI.

### Key observation

The service behaved like a **BBS login** and accepted **any password string**.

This mattered because it meant authentication was intentionally weak for the first hop; the goal was clearly enumeration, not password guessing.

### Result

After logging in as a simple user such as `guest`, the service presented a menu-driven interface with options like:

- files/library
- chat/sysop
- news
- menu/help
- goodbye/logoff

This confirmed that the target was intentionally styled as an old bulletin board system.

---

## Step 3 - Enumerate the BBS menus

The next step was to inspect every menu option and look for:

- clues pointing to another service
- downloadable files
- user/account distinctions
- any hidden or protected area

### Important observations from the BBS

During enumeration, two details stood out:

1. There was a hint that the **“good stuff moved to a protected dir”**
2. The file library advertised **ZMODEM transfers**

That made the BBS feel like a partial environment rather than the final destination.

### Why this mattered

- The “protected dir” message suggested there was hidden content elsewhere
- ZMODEM indicated the challenge author wanted the player to notice old transfer mechanisms
- However, even if the BBS was thematic, it did not immediately yield the flag

The BBS was likely just one hop in the chain.

---

## Step 4 - Try the file transfer angle

Because the file library exposed downloadable items and mentioned ZMODEM, it was reasonable to try downloading the accessible files.

### What happened

- Some file entries initiated a ZMODEM transfer
- A locked/protected item existed as well
- The environment initially lacked `rz`, so `lrzsz` was installed to support ZMODEM

### Observation

Although this was a plausible route, the transfers did not produce the decisive next artifact quickly. The challenge was clearly broader than just the BBS itself.

### Why this pivoted

In CTFs, if a service is only giving partial clues and the description emphasizes multiple protocols, it is smart to scan the host for additional exposed ports.

So instead of overcommitting to ZMODEM, the attack surface expanded.

---

## Step 5 - Scan for other services

A port scan revealed that the host exposed more than just the BBS.

### Important services discovered

- `80` - Apache default page
- `8080` - custom web content
- `2222` - SSH-like service
- `5000` - web application
- `5001` - another web application

This matched the challenge description very well: packets being routed through multiple protocols from different eras.

---

## Step 6 - Inspect the web service on port 8080

This was the first major breakthrough.

Fetching the content on `http://23.179.17.92:8080/` revealed something highly sensitive:

### Critical observation

The page exposed an **OpenSSH private key**.

It also embedded a clue pointing to:

```text
ctf@23.179.17.92:2222
```

That meant:

- the key was likely intended for the next hop
- the target account was probably `ctf`
- the next protocol in the chain was SSH

### Why this was important

Leaking a private key is a classic pivot mechanism in multi-stage challenges. It is much more specific than a generic clue, so from this point onward port `2222` became the primary path.

---

## Step 7 - Use the leaked key against port 2222

The private key was saved locally and inspected.

### Observations

- The key fingerprint looked valid
- The key comment / associated clue confirmed the target looked like `ctf@23.179.17.92:2222`
- Port `2222` was open

A normal SSH client connection did not behave like a standard Linux shell session. Instead, the service looked custom and somewhat unstable for normal interactive shell assumptions.

To get finer control, a Python SSH client (`paramiko`) was used.

### Critical observation

The SSH service authenticated the key successfully, but instead of a shell, it returned an **HTTP response**:

- HTTP-like status line
- custom server banner such as `jailHTTPd/0.1`
- content indicating the user was inside a restricted web root

This was one of the core challenge twists.

---

## Step 8 - Understand the SSH hop: an HTTP jail, not a shell

Once connected through SSH, the service acted like a tiny jailed HTTP daemon rather than a command shell.

### Key observations

- It returned responses such as `HTTP/1.0 200 OK`
- It identified itself as something like:

  ```text
  Server: jailHTTPd/0.1 (PROTOTYPE - DO NOT EXPOSE)
  ```

- It suggested a root like `/var/www/html`
- Requesting `/` listed only a single visible file: `not_a_flag`

### What this suggested

The 1986 hint in the challenge description likely referred to **old HTTP behavior / RFC-era protocol quirks**, because HTTP/1.0 is historically close to that period and the service explicitly wanted raw HTTP-style interaction.

The file `not_a_flag` was an intentional decoy.

---

## Step 9 - Probe the jailHTTPd service

At this stage, there were two reasonable hypotheses:

1. The flag was hidden behind a **path parsing bug**, directory traversal, or old HTTP quirk in `jailHTTPd`
2. The SSH/HTTP jail was only part of the theme, and another exposed web app contained the actual secret

Both were investigated.

### Tests tried against the SSH HTTP jail

A variety of requests were sent manually, including:

- normal paths such as `/flag`, `/secret`, `/protected`, `/uploads`
- case-variant directory names like `/UPLOADS/`
- dot-paths such as `/./...`
- encoded traversal variants such as `%2e`, `%2e%2e`, `%2f`, double-encoded forms
- alternate HTTP versions such as `HTTP/0.9`
- multiple slash variants like `//` and `///`

### Observations

- The service responded oddly in places
- Some paths produced unusual behavior
- Traversal-like requests produced forbidden or not found responses
- No direct request yielded the flag

### Conclusion

This looked intentionally suspicious, but no concrete exploit path emerged from the jail alone. That meant the remaining exposed web applications still needed serious attention.

---

## Step 10 - Enumerate ports 5000 and 5001

The two modern-looking web apps were then inspected.

### Port 5000

This appeared to be a login / account-oriented web app, referred to during solving as something like **SecureVault**.

### Port 5001

This exposed user registration/login plus a report feature.

Both were plausible targets because multi-stage CTFs often end with:

- broken authentication
- IDOR
- insecure reset flows
- hidden administrative content

---

## Step 11 - Test port 5000 (SecureVault-style app)

The app on port `5000` was probed for:

- login weaknesses
- default credentials
- forgot-password behavior
- reset-password logic
- existence leaks in user recovery
- hidden routes like `/admin`, `/dashboard`, `/config`, etc.

### Observation

This app did not yield a useful compromise quickly.

For example:

- guessed usernames often returned “No account associated with that username”
- attempted logins only produced standard failures
- no obvious reset token disclosure or admin bypass appeared in the tested surface

### Conclusion

Port 5000 was a plausible red herring or at least not the easiest intended route.

---

## Step 12 - Register on port 5001 and inspect the report functionality

The app on port `5001` allowed registration and login, so a fresh low-privilege account was created.

Once authenticated, the report feature became the main focus.

### Why this mattered

Any feature that loads objects by numeric ID is a prime candidate for:

- **IDOR** (Insecure Direct Object Reference)
- weak access checks
- leaked seeded data from other users or admins

This was especially attractive because the rest of the challenge had already emphasized hidden/protected content.

---

## Step 13 - Confirm the IDOR behavior

The report viewer used a numeric `id` parameter, e.g. something like:

```text
/report?id=NUMBER
```

After authentication, requesting various report IDs showed that the application returned reports not necessarily belonging to the current user.

### Critical observation

This is textbook **authenticated IDOR**:

- the user is logged in
- but authorization checks are missing or insufficient
- so arbitrary report IDs can be viewed by changing the `id` parameter

This matched the theme of the final flag exactly.

### Early results

Lower report IDs showed generic or fake seeded reports such as “Fake report #1” and similar placeholders.

That told us two things:

1. The endpoint was definitely reading real records by ID
2. The database likely contained seeded content beyond the obviously fake entries

---

## Step 14 - Enumerate report IDs

The next step was straightforward: sweep a range of report IDs while authenticated and look for anything that was:

- not fake filler
- not user-generated junk
- containing `CIT{`
- containing strong clues to the next path

### Practical methodology

The report pages were fetched in bulk and the rendered text was searched for:

- `CIT{`
- words like `flag`, `secret`, `admin`, `protected`
- content distinct from the repeated “Fake report #N” entries

### Important observation

One of the report IDs, specifically:

```text
report?id=347
```

contained the flag.

---

## Step 15 - Retrieve the flag

The flag recovered from the report viewer was:

```text
CIT{Acc355_C0ntr0l_M@tt3rs!}
```

This is a direct thematic match for the vulnerability used to obtain it:

- the report endpoint exposed records to authenticated users
- but failed to enforce object-level access control
- therefore a normal user could read privileged or unrelated content

That is exactly what **“Access Control Matters”** refers to.

---

## Why the challenge was designed this way

This challenge was more than a single bug hunt. It was a staged exploration challenge with misdirection and protocol-themed pivots.

### Design themes used by the author

- **Retro networking / BBS flavor** to set the mood
- **Protocol hopping** across telnet-like text UI, ZMODEM hints, SSH, and HTTP
- **A leaked private key** as a transition mechanism
- **A fake/restricted HTTP jail** to pull attention toward older HTTP semantics
- **A modern web app with IDOR** as the real final vulnerability

### Why the SSH HTTP jail mattered even though it wasn’t the final exploit

It served several purposes:

1. It validated the “different protocols” theme
2. It made the 1986/manual clue feel relevant
3. It consumed attention and encouraged careful manual interaction
4. It prevented the challenge from being solved by only checking the obvious first port

In other words, it was an intentional intermediate hop, not just noise.

---

## Key observations and pivots summarized

### Observation 1: `./files` was empty
This implied the challenge was remote-service-driven.

### Observation 2: Port `2323` hosted a BBS-like interface
This matched the retro hint and began the chain.

### Observation 3: The BBS hinted at protected content and old transfer methods
Useful thematically, but not the final route.

### Observation 4: Port scan exposed more services
Essential pivot. Without scanning, the real path would have been missed.

### Observation 5: Port `8080` leaked a private SSH key
This was the clearest intentional handoff to the next stage.

### Observation 6: Port `2222` was not a normal shell
The custom SSH service returned HTTP, indicating a jailed environment.

### Observation 7: The SSH jail exposed only `not_a_flag`
A deliberate decoy to encourage additional exploration.

### Observation 8: Port `5001` allowed authenticated access to reports by ID
This was the real vulnerability surface.

### Observation 9: Report IDs were enumerable and improperly protected
This confirmed IDOR / broken access control.

### Observation 10: Report `347` contained the flag
Final exploit success.

---

## Vulnerability analysis

The final exploitable bug was:

## Authenticated IDOR / Broken Object-Level Authorization

### Typical vulnerable logic
A backend often does something like:

```python
report = Report.query.get(request.args['id'])
return render_template('report.html', report=report)
```

but forgets to verify:

```python
report.owner_id == current_user.id
```

or equivalent authorization rules.

### Secure logic should require
- object ownership check
- role-based authorization for privileged reports
- deny-by-default access policy
- non-sequential identifiers if possible
- monitoring for enumeration patterns

### Impact
Any authenticated user can read:
- other users’ reports
- internal seeded reports
- secrets accidentally stored in report records
- flags in a CTF context

---

## Lessons learned

1. **Always scan the whole target** when a challenge mentions multiple protocols.
2. **Do not overcommit to the first thematic clue**; the BBS and ZMODEM were real, but not the final exploit.
3. **Leaked credentials/keys are often intentional pivot artifacts** in staged challenges.
4. **Custom services over standard protocols** often require manual/raw interaction.
5. **IDOR remains one of the most common and damaging web vulnerabilities**.
6. **Authenticated does not mean authorized**.

---

## Minimal solve path

If I were to summarize the shortest path after knowing the answer:

1. Read the description and connect to `23.179.17.92:2323`
2. Realize the challenge is multi-service and scan the host
3. Inspect port `8080` and extract the leaked private key
4. Use the key with user `ctf` against port `2222`
5. Observe the custom HTTP jail and recognize it may be a distraction/intermediate stage
6. Register/login on port `5001`
7. Enumerate `/report?id=...` while authenticated
8. Find the flag at report ID `347`

---

## Flag

```text
CIT{Acc355_C0ntr0l_M@tt3rs!}
```
