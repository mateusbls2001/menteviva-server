from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import subprocess
import os
import uuid
import random

app = Flask(__name__)

# Configs
OUTPUT_DIR = "/tmp/menteviva_videos"
MUSIC_DIR = "/app/music"  # repo root /music → /app/music in container
VIDEO_DURATION = 10  # seconds
FONT_SIZE = 32
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Colors
WHITE = (245, 245, 243)
BLACK = (10, 10, 11)
ACCENT = (160, 160, 155)

def get_random_music():
    """Pick a random .mp3 from /app/music/"""
    try:
        files = [f for f in os.listdir(MUSIC_DIR) if f.endswith('.mp3') or f.endswith('.wav')]
        if files:
            return os.path.join(MUSIC_DIR, random.choice(files))
    except:
        pass
    return None

def wrap_text(text, max_chars=28):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def create_frame(phrase):
    img = Image.new('RGB', (1080, 1080), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    W, H = img.size

    JB_MONO = "/usr/share/fonts/truetype/jetbrains/JetBrainsMono-Bold.ttf"
    JB_MONO_REG = "/usr/share/fonts/truetype/jetbrains/JetBrainsMono-Regular.ttf"
    FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FALLBACK_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        font = ImageFont.truetype(JB_MONO, FONT_SIZE)
        font_handle = ImageFont.truetype(JB_MONO_REG, 28)
    except:
        try:
            font = ImageFont.truetype(FALLBACK, FONT_SIZE)
            font_handle = ImageFont.truetype(FALLBACK_REG, 28)
        except:
            font = ImageFont.load_default()
            font_handle = font

    lines = wrap_text(phrase, max_chars=26)
    line_height = FONT_SIZE + 16
    total_height = len(lines) * line_height

    pad_v = 50
    pad_h = 70
    y_start = (H - total_height) // 2 - pad_v

    img = img.convert('RGB')
    draw = ImageDraw.Draw(img)

    y = y_start + pad_v
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        tw = bb[2] - bb[0]
        x = (W - tw) // 2
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=WHITE)
        y += line_height

    line_y = y_start + total_height + pad_v * 2 + 10
    draw.rectangle([pad_h + 40, line_y, W - pad_h - 40, line_y + 1], fill=ACCENT)

    handle = "@menteviva_01"
    bb_h = draw.textbbox((0, 0), handle, font=font_handle)
    tw_h = bb_h[2] - bb_h[0]
    draw.text(((W - tw_h) // 2, H - 80), handle, font=font_handle, fill=ACCENT)

    return img

def image_to_video(img, output_path, duration=VIDEO_DURATION):
    frame_path = f"/tmp/{uuid.uuid4()}.png"
    img.save(frame_path, 'PNG')

    music_path = get_random_music()

    if music_path:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", frame_path,
            "-i", music_path,
            "-vf", f"fade=in:0:15,fade=out:st={duration-1}:d=1,scale=1080:1080",
            "-af", f"afade=in:st=0:d=1,afade=out:st={duration-1}:d=1",
            "-c:v", "libx264",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-shortest",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", frame_path,
            "-vf", f"fade=in:0:15,fade=out:st={duration-1}:d=1,scale=1080:1080",
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(frame_path)

    if result.returncode != 0:
        raise Exception(f"FFmpeg error: {result.stderr}")

    return output_path

# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "menteviva-video-generator"})

@app.route('/generate-image', methods=['POST'])
def generate_image():
    data = request.get_json()
    if not data or 'phrase' not in data:
        return jsonify({"error": "Campo 'phrase' obrigatório"}), 400
    phrase = data.get('phrase', '').strip()
    if not phrase:
        return jsonify({"error": "Frase não pode ser vazia"}), 400
    try:
        frame = create_frame(phrase)
        img_id = str(uuid.uuid4())
        output_path = os.path.join(OUTPUT_DIR, f"{img_id}.png")
        frame.save(output_path, 'PNG')
        return send_file(output_path, mimetype='image/png', as_attachment=True,
                         download_name=f"menteviva_{img_id}.png")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/generate-image-url', methods=['POST'])
def generate_image_url():
    data = request.get_json()
    if not data or 'phrase' not in data:
        return jsonify({"error": "Campo 'phrase' obrigatório"}), 400
    phrase = data.get('phrase', '').strip()
    try:
        frame = create_frame(phrase)
        img_id = str(uuid.uuid4())
        output_path = os.path.join(OUTPUT_DIR, f"{img_id}.png")
        frame.save(output_path, 'PNG')
        base_url = request.host_url.rstrip('/').replace('http://', 'https://')
        return jsonify({"success": True, "image_url": f"{base_url}/image/{img_id}",
                        "image_id": img_id, "phrase": phrase})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/image/<image_id>', methods=['GET'])
def get_image(image_id):
    try:
        uuid.UUID(image_id)
    except ValueError:
        return jsonify({"error": "Invalid image ID"}), 400
    path = os.path.join(OUTPUT_DIR, f"{image_id}.png")
    if not os.path.exists(path):
        return jsonify({"error": "Image not found"}), 404
    return send_file(path, mimetype='image/png')

@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    if not data or 'phrase' not in data:
        return jsonify({"error": "Campo 'phrase' obrigatório"}), 400
    phrase = data.get('phrase', '').strip()
    duration = int(data.get('duration', VIDEO_DURATION))
    if not phrase:
        return jsonify({"error": "Frase não pode ser vazia"}), 400
    if len(phrase) > 200:
        return jsonify({"error": "Frase muito longa (máx 200 chars)"}), 400
    try:
        frame = create_frame(phrase)
        video_id = str(uuid.uuid4())
        output_path = os.path.join(OUTPUT_DIR, f"{video_id}.mp4")
        image_to_video(frame, output_path, duration)
        return send_file(output_path, mimetype='video/mp4', as_attachment=True,
                         download_name=f"menteviva_{video_id}.mp4")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/generate-url', methods=['POST'])
def generate_url():
    data = request.get_json()
    if not data or 'phrase' not in data:
        return jsonify({"error": "Campo 'phrase' obrigatório"}), 400
    phrase = data.get('phrase', '').strip()
    duration = int(data.get('duration', VIDEO_DURATION))
    try:
        frame = create_frame(phrase)
        video_id = str(uuid.uuid4())
        output_path = os.path.join(OUTPUT_DIR, f"{video_id}.mp4")
        image_to_video(frame, output_path, duration)
        base_url = request.host_url.rstrip('/').replace('http://', 'https://')
        return jsonify({"success": True, "video_url": f"{base_url}/video/{video_id}",
                        "video_id": video_id, "phrase": phrase})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/video/<video_id>', methods=['GET'])
def get_video(video_id):
    try:
        uuid.UUID(video_id)
    except ValueError:
        return jsonify({"error": "Invalid video ID"}), 400
    path = os.path.join(OUTPUT_DIR, f"{video_id}.mp4")
    if not os.path.exists(path):
        return jsonify({"error": "Video not found"}), 404
    return send_file(path, mimetype='video/mp4')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

@app.route('/debug-music', methods=['GET'])
def debug_music():
    try:
        files = os.listdir(MUSIC_DIR)
        return jsonify({"path": MUSIC_DIR, "files": files})
    except Exception as e:
        return jsonify({"error": str(e)})
