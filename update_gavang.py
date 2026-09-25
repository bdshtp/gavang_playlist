import os
import re
import time
import requests
from io import BytesIO
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

API_URL = "https://gavangtv-api.adviceme.io/api/v1/matches"
OUTPUT_FILE = "gavang.m3u"
LOGO_DIR = "logos/gavang"
BASE_URL = "https://bdshtp.github.io/gavang_playlist"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://gavang33.uk",
    "Referer": "https://gavang33.uk/"
}

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def parse_gavang_datetime(match, slug):
    value = match.get("matchTime")
    if value:
        try:
            ts = int(value)
            if ts > 100000000000:
                ts /= 1000
            return datetime.fromtimestamp(ts, VN_TZ)
        except Exception:
            pass

    date_value = match.get("matchDate")
    time_value = match.get("matchTime")
    if date_value and isinstance(date_value, str):
        try:
            # Support YYYYMMDD
            if re.fullmatch(r"\d{8}", date_value):
                return datetime.strptime(date_value, "%Y%m%d").replace(tzinfo=VN_TZ)
        except Exception:
            pass

    m = re.search(r"luc-(\d{4})", slug)
    if m:
        now = datetime.now(VN_TZ)
        return now.replace(hour=int(m.group(1)[:2]), minute=int(m.group(1)[2:]), second=0, microsecond=0)

    return None


def download_logo(url):
    if not url:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        print(f"Logo lỗi: {url} - {e}")
        return None


def create_logo_image(home_logo, away_logo, output_file):
    width, height = 600, 300
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))

    home = download_logo(home_logo)
    away = download_logo(away_logo)

    if home:
        home.thumbnail((210, 210), Image.Resampling.LANCZOS)
        canvas.alpha_composite(home, (60 + (210-home.width)//2, 45 + (210-home.height)//2))

    if away:
        away.thumbnail((210, 210), Image.Resampling.LANCZOS)
        canvas.alpha_composite(away, (330 + (210-away.width)//2, 45 + (210-away.height)//2))

    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except Exception:
        font = ImageFont.load_default()

    text = "VS"
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((width-(box[2]-box[0]))/2, (height-(box[3]-box[1]))/2-5),
              text, fill=(0, 0, 0, 255), font=font)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    canvas.convert("RGB").save(output_file, "PNG", optimize=True)


def main():
    params = {"webType": "gavang", "t": int(time.time() * 1000)}
    response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    result = response.json()

    if not result.get("success"):
        raise RuntimeError("API Gavang trả về lỗi")

    data = result.get("data", {})
    playlist = []
    seen = set()

    for slug, match in data.items():
        dt = parse_gavang_datetime(match, slug)
        if not dt:
            continue

        home_team = match.get("homeTeam", {})
        away_team = match.get("awayTeam", {})
        home = home_team.get("name", "Home").strip()
        away = away_team.get("name", "Away").strip()

        stream_url = None
        for anchor in match.get("anchorAppointmentVoList", []):
            for url in anchor.get("streamUrls", []):
                if isinstance(url, str) and ".m3u8" in url:
                    stream_url = url
                    break
            if stream_url:
                break

        if not stream_url:
            default_link = match.get("defaultLink", "")
            if isinstance(default_link, str) and ".m3u8" in default_link:
                stream_url = default_link

        if not stream_url:
            continue

        match_id = str(match.get("matchId") or slug)
        unique = (match_id, stream_url)
        if unique in seen:
            continue
        seen.add(unique)

        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", match_id)
        logo_file = f"{LOGO_DIR}/{safe_id}.png"
        create_logo_image(home_team.get("logo", ""), away_team.get("logo", ""), logo_file)

        title = f"{dt.strftime('%d/%m %H:%M')} | {home} vs {away}"
        logo_url = f"{BASE_URL}/{logo_file}"

        playlist.append({
            "dt": dt,
            "title": title,
            "logo": logo_url,
            "url": stream_url
        })

    playlist.sort(key=lambda x: x["dt"])

    if not playlist:
        raise RuntimeError("Không tìm thấy trận Gavang có link M3U8.")

    lines = ["#EXTM3U"]
    for item in playlist:
        lines.append(
            f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="Gavang",{item["title"]}'
        )
        lines.append(item["url"])

    Path(OUTPUT_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Gavang: {len(playlist)} trận")
    for item in playlist:
        print("-", item["title"])


if __name__ == "__main__":
    main()
