# Raspberry Pi Setup

Use these steps on the Raspberry Pi terminal inside the project folder.

## 1. Install system packages

```bash
sudo apt update
sudo xargs apt install -y < raspi_system_packages.txt
```

## 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

## 3. Install Python dependencies

```bash
pip install -r requirements.raspi.txt
```

## 4. Create the Pi env file

```bash
cp .env.raspi .env
```

Then edit `.env` and add your real provider keys.

## 5. Run the app

```bash
python main.py
```

## 6. Run the hardware check

Inside the app, run:

```text
pi self test
```

## Notes

- This Pi profile is tuned for `Raspberry Pi 3B+`.
- `Live mode` is disabled by default on Pi 3 to keep the device responsive.
- `Whisper tiny` is used because Pi 3B+ is limited.
- For a Pi 4 or Pi 5, you can raise frame size and speech model later.
