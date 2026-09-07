# local-site

A tiny home-lab, learning-purposes tool: give it any website link and it
copies that site's static front-end files (HTML, CSS, JS, images, fonts)
to a local folder. It only copies files — **no database** and no
server-side code — so the result is a plain static site you can drop
into XAMPP's `htdocs` or serve with any "live server".

## Setup

```bash
pip install -r requirements.txt
```

## Usage

Clone a single page and its assets:

```bash
python3 clone_site.py https://example.com -o output
```

Also follow same-site links to clone a few extra pages:

```bash
python3 clone_site.py https://example.com -o output --follow-links --max-pages 5
```

The cloned files are written under `output/<site-domain>/...`, with all
CSS/JS/image links rewritten to relative paths so the copy works
completely offline.

## Serving the cloned site locally

Pick whichever you already have available:

- **XAMPP**: copy the folder printed by the tool (e.g.
  `output/example.com`) into your XAMPP `htdocs` directory, start
  Apache from the XAMPP control panel, then open
  `http://localhost/example.com/` in your browser.
- **Python's built-in server** (no install needed):
  ```bash
  cd output/example.com
  python3 -m http.server 8000
  ```
  then open `http://localhost:8000/`.
- **Node "live-server"** (auto-reloads on file changes):
  ```bash
  npx live-server output/example.com
  ```

## Running the tests

```bash
python3 -m unittest discover -s tests
```
