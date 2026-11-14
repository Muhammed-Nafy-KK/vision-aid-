# Blind Assist

`Blind Assist` is a Python voice-first assistant for blind or low-vision users. It combines a camera, local speech tools, and Gemini vision models to help with:

- scene description
- obstacle-aware navigation hints
- continuous safety scan mode
- reading visible text
- locating visible objects
- asking questions about the current scene
- optional Gemini Live streaming guidance

## Important limits

This is a useful assistive prototype, not a certified mobility or medical device. It can miss hazards, hallucinate, or be delayed by camera, microphone, network, or model issues. It should not be the only safety tool used for street crossing or dangerous environments.

## Setup

1. Activate your virtual environment.
2. Put your provider keys in a `.env` file:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.0-flash,gemini-2.0-flash-lite,gemini-flash-latest
OPENAI_API_KEYS=your_openai_key_1,your_openai_key_2
OPENAI_VISION_MODEL=gpt-4o-mini
DEEPSEEK_API_KEYS=your_deepseek_key_1,your_deepseek_key_2
DEEPSEEK_VISION_MODEL=
PROVIDER_ORDER=gemini,openai,deepseek
NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
OSRM_BASE_URL=https://router.project-osrm.org
DEVICE_PROFILE=pc
```

3. Install dependencies if needed:

```powershell
vision_ai_env\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
vision_ai_env\Scripts\python.exe main.py
```

## Raspberry Pi 3B+ Mode

The project now has a lighter Pi profile. To prepare a Raspberry Pi 3B+ build, set these values in `.env`:

```env
DEVICE_PROFILE=pi3
CAMERA_BACKEND=v4l2
FRAME_WIDTH=320
FRAME_HEIGHT=240
CAMERA_READ_INTERVAL_SECONDS=0.08
WHISPER_MODEL=tiny
WHISPER_BEAM_SIZE=1
LIVE_INTERVAL_SECONDS=5.0
ASSIST_INTERVAL_SECONDS=4.5
ENABLE_LIVE_MODE=false
```

This keeps the Pi 3B+ more responsive by lowering camera load, using a smaller speech model, and disabling the heaviest live-streaming mode by default.

There are also Pi-specific files in the project root:

- [requirements.raspi.txt](C:/Users/aysha/OneDrive/Documents/New%20folder/requirements.raspi.txt:1)
- [raspi_system_packages.txt](C:/Users/aysha/OneDrive/Documents/New%20folder/raspi_system_packages.txt:1)
- [.env.raspi](C:/Users/aysha/OneDrive/Documents/New%20folder/.env.raspi:1)
- [RASPBERRY_PI_SETUP.md](C:/Users/aysha/OneDrive/Documents/New%20folder/RASPBERRY_PI_SETUP.md:1)

## Commands

- `describe`
- `navigate`
- `read`
- `safety`
- `crossing`
- `find bottle`
- `ask is there an empty chair here`
- `assist on`
- `assist off`
- `live on`
- `live off`
- `set location MG Road Bengaluru`
- `route to City Railway Station`
- `route from MG Road Bengaluru to Cubbon Park`
- `next step`
- `previous step`
- `repeat step`
- `route status`
- `restart route`
- `destination`
- `stop route`
- `voice on`
- `voice off`
- `listen`
- `audio test`
- `pi self test`
- `sos`
- `status`
- `quit`

## Provider Fallback

Image analysis now tries providers in order:

1. Gemini keys and Gemini models
2. OpenAI-compatible vision keys
3. DeepSeek-compatible vision keys if you set a vision-capable model

Live mode remains Gemini-only.

## Outdoor Navigation

Outdoor route guidance uses no-key OpenStreetMap services. The app uses Nominatim for place search and OSRM for walking directions, then reads the route step by step. Public endpoints can still be slow or rate-limited, so for heavier real-world use a self-hosted or paid routing backend is safer.

## Smart Cane Features

- `assist on` starts continuous safety checks every few seconds
- `safety` asks for a one-shot hazard warning
- `crossing` asks for road-crossing guidance
- `sos` reads the saved emergency contact and last saved location
- `sos` also saves a text emergency report to `alerts/last_sos.txt`
- `pi self test` checks mic, camera, speaker queue, SOS folder, and map network access
- if cloud vision fails, the app falls back to a basic local camera safety hint

## Files

- `main.py`: app entry point
- `blind_assist/app.py`: command loop and orchestration
- `blind_assist/gemini_service.py`: Gemini image and live streaming integration
- `blind_assist/speech.py`: text-to-speech and local speech-to-text
- `blind_assist/camera.py`: camera capture
