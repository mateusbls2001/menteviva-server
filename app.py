from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import subprocess
import tempfile
import os
import uuid
import textwrap

app = Flask(__name__)

# Configs
TEMPLATE_PATH = "template.png"
OUTPUT_DIR = "/tmp/menteviva_videos"
VIDEO_DURATION = 8  # seconds
FONT_SIZE = 58
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Colors
WHITE = (245, 245, 243)
BLACK = (10, 10, 11)
ACCENT = (160, 160, 155)

def wrap_text(text, max_chars=28):
    """Wrap text into lines"""
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
    """Create image frame with phrase text"""
    img = Image.open(TEMPLATE_PATH).copy()
    draw = ImageDraw.Draw(img)
    W, H = img.size

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", FONT_SIZE)
        font_handle = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        font = ImageFont.load_default()
        font_handle = font

    # Wrap text — keep original case, no uppercase
    lines = wrap_text(phrase, max_chars=26)
    line_height = FONT_SIZE + 16
    total_height = len(lines) * line_height

    # Center vertically with padding
    pad_v = 50
    pad_h = 70
    y_start = (H - total_height) // 2 - pad_v

    # Dark overlay behind text only
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        [pad_h - 20, y_start,
         W - pad_h + 20, y_start + total_height + pad_v * 2],
        fill=(0, 0, 0, 200)
    )
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(img)

    # Draw text lines centered
    y = y_start + pad_v
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        tw = bb[2] - bb[0]
        x = (W - tw) // 2
        # Subtle shadow
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        # Main white text
        draw.text((x, y), line, font=font, fill=WHITE)
        y += line_height

    # Thin accent line below text block
    line_y = y_start + total_height + pad_v * 2 + 10
    draw.rectangle([pad_h + 40, line_y, W - pad_h - 40, line_y + 1], fill=ACCENT)

    # @menteviva handle centered at bottom
    handle = "@menteviva"
    bb_h = draw.textbbox((0, 0), handle, font=font_handle)
    tw_h = bb_h[2] - bb_h[0]
    draw.text(((W - tw_h) // 2, H - 80), handle, font=font_handle, fill=ACCENT)

    return img

def image_to_video(img, output_path, duration=VIDEO_DURATION):
    """Convert PIL image to MP4 using FFmpeg"""
    # Save temp frame
    frame_path = f"/tmp/{uuid.uuid4()}.png"
    img.save(frame_path, 'PNG')

    # FFmpeg command: image → video with fade in/out
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", frame_path,
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

@app.route('/generate', methods=['POST'])
def generate():
    """
    POST /generate
    Body: { "phrase": "Sua frase aqui", "duration": 8 }
    Returns: MP4 video file
    """
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
        # Generate frame
        frame = create_frame(phrase)

        # Convert to video
        video_id = str(uuid.uuid4())
        output_path = os.path.join(OUTPUT_DIR, f"{video_id}.mp4")
        image_to_video(frame, output_path, duration)

        # Return video file
        return send_file(
            output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f"menteviva_{video_id}.mp4"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/generate-url', methods=['POST'])
def generate_url():
    """
    Same as /generate but returns a URL instead of file
    Useful for Make → pass URL to Instagram module
    """
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

        # Return the video ID so it can be fetched
        base_url = request.host_url.rstrip('/')
        return jsonify({
            "success": True,
            "video_url": f"{base_url}/video/{video_id}",
            "video_id": video_id,
            "phrase": phrase
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/video/<video_id>', methods=['GET'])
def get_video(video_id):
    """Serve generated video by ID"""
    # Security: only allow valid UUIDs
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
