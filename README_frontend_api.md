# ECAG2 Realtime ECG Frontend

This branch adds a static ECG monitor frontend and a lightweight local API
that reads the existing `data/scenarios/*.npz` files.

## Run locally

Start the API:

```bash
python3 api_server.py
```

Start the static frontend from this repository root in a second terminal:

```bash
python3 -m http.server 4173
```

Open:

```text
http://127.0.0.1:4173
```

The frontend connects to:

```text
http://127.0.0.1:8000
```

If the API is not running, the page falls back to offline mock waveform data.
