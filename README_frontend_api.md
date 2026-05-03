# ECAG2 Heart Wellness Landing Page

This branch adds a responsive React + Tailwind CSS website for ECAG2. The visual direction is a
modern wellness-tech landing page: large editorial typography, soft rounded cards, clean white
space, and pastel health dashboard modules.

The page uses the existing GitHub repository data through a lightweight local API:

- `data/scenarios/mit100_normal.npz`
- `data/scenarios/mit207_severe.npz`
- `data/scenarios/mit208_pvc.npz`
- `data/scenarios/vf418_arrest.npz`

## Run locally

Install frontend dependencies:

```bash
npm install
```

Start the ECG data API:

```bash
python3 api_server.py
```

Start the React website in a second terminal:

```bash
npm run dev
```

Open the Vite URL shown in the terminal, usually:

```text
http://127.0.0.1:5173
```

If the API is not running, the website falls back to bundled demo values.
