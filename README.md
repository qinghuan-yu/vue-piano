# A-Melody-Annotator

A powerful web tool for automatically identifying and manually annotating main melodies from complex piano MIDI files.

## Features

- 🎹 Automatically uses the Skyline algorithm to initially identify the main melody
- 🎨 Intuitive Piano Roll view
- ✏️ Supports batch editing via click and selection
- 🎵 Real-time playback preview (melody can be played individually)
- 📥 Export multi-track MIDI files (melody track + accompaniment track)

## Technology Stack

### Frontend
- Vue 3 (Script Setup)
- Vite
- HTML5 Canvas
- Tone.js 

### Backend
- Python FastAPI
- pretty_midi

## Project Structure

```
vue-piano/
├── backend/              # Python FastAPI 
│   ├── main.py          # Main program
│   └── requirements.txt # Python dependencies
├── frontend/            # Vue 3 frontend
│   ├── src/
│   │   ├── components/
│   │   │   └── PianoRoll.vue  # Piano Roller Component
│   │   ├── App.vue
│   │   └── main.js
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## Quick Start

### Backend Startup

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend Startup

```bash
cd frontend
npm install
npm run dev
```

## Usage

1. Upload MIDI file
2. The system automatically labels the main melody (green) and accompaniment (gray)
3. Manually click or select to correct annotations
4. Play Preview (Solo Melody mode available)
5. Export split-track MIDI file

## API Documentation

### POST /upload
Uploads a MIDI file and returns the analyzed note data.

### POST /export
Exports the split-track MIDI file.

## License

MIT
