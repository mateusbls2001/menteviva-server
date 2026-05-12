FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-dejavu-core \
    wget \
    unzip \
    fontconfig \
    && wget -q https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip -O /tmp/jbmono.zip \
    && unzip -q /tmp/jbmono.zip -d /tmp/jbmono \
    && mkdir -p /usr/share/fonts/truetype/jetbrains \
    && cp /tmp/jbmono/fonts/ttf/*.ttf /usr/share/fonts/truetype/jetbrains/ \
    && fc-cache -f -v \
    && rm -rf /tmp/jbmono* \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:8080 --workers 2 --timeout 120"]
