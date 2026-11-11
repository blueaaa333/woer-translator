"""Real offline Piper WAV smoke for the gated Windows CI draft."""
import argparse
import io
import json
import subprocess
import wave
from pathlib import Path


def synthesize(runtime, models, accent, word="water"):
    label = "uk" if accent == 1 else "us"
    folder = Path(models) / label
    model, config = folder / "dictionary-voice.onnx", folder / "dictionary-voice.onnx.json"
    if not model.is_file() or not config.is_file():
        raise FileNotFoundError(f"Missing complete {label} model/config pair")
    command = [
        str(Path(runtime) / "piper.exe"), "--model", str(model), "--config", str(config),
        "--espeak_data", "espeak-ng-data", "--json-input", "--output_file", "-",
        "--length_scale", "1.05", "--quiet",
    ]
    result = subprocess.run(
        command, cwd=runtime, input=(json.dumps({"text": word}) + "\n").encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=True,
    )
    with wave.open(io.BytesIO(result.stdout), "rb") as audio:
        params, pcm = audio.getparams(), audio.readframes(audio.getnframes())
    if params.sampwidth != 2 or params.nframes <= 0 or not any(pcm):
        raise ValueError(f"Invalid or silent {label} output")
    return {"accent": label, "sample_rate": params.framerate, "channels": params.nchannels,
            "frames": params.nframes, "pcm_bytes": len(pcm)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = {"offline": True, "results": [synthesize(args.runtime, args.models, accent) for accent in (1, 2)]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
