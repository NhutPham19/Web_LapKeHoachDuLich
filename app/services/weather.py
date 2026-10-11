import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from app.contracts import (
    PROVINCE_COORDS,
    VN_UTC_OFFSET_HOURS,
    WEATHER_CACHE_TTL_HOURS,
    WeatherDay,
)


def fetch_raw(province: str) -> dict:
    """
    Gọi OpenWeatherMap API /data/2.5/forecast qua urllib.request.
    Key đọc từ os.environ['OPENWEATHER_API_KEY'].
    """
    coords = PROVINCE_COORDS.get(province)
    if not coords:
        raise ValueError(f"Tỉnh không hợp lệ: {province}")

    lat, lon = coords
    api_key = os.environ.get("OPENWEATHER_API_KEY", "")
    if not api_key:
        raise ValueError("Chưa cấu hình biến môi trường OPENWEATHER_API_KEY")

    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric",
        "lang": "vi",
    }
    url = f"https://api.openweathermap.org/data/2.5/forecast?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(url, headers={"User-Agent": "DuLich-App/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_forecast(raw: dict, start_date: date, days: int) -> list[WeatherDay]:
    """
    Hàm thuần: Chuyển đổi dữ liệu thô từ OpenWeatherMap thành danh sách WeatherDay.
    - Mốc thời gian đổi sang giờ VN (+7).
    - Gán slot: 6-11 -> morning, 12-17 -> afternoon, 18-21 -> evening.
    - Chỉ trả về các ngày trong [start_date, start_date + days) có dữ liệu.
    """
    items = raw.get("list", [])
    if not items:
        return []

    target_dates = {start_date + timedelta(days=i) for i in range(days)}
    vn_tz = timezone(timedelta(hours=VN_UTC_OFFSET_HOURS))

    # Nhóm dữ liệu theo ngày VN
    day_data: dict[date, list[tuple[datetime, dict]]] = {}
    for item in items:
        dt_val = item.get("dt")
        if not dt_val:
            continue
        dt_vn = datetime.fromtimestamp(dt_val, tz=timezone.utc).astimezone(vn_tz)
        item_date = dt_vn.date()
        if item_date in target_dates:
            day_data.setdefault(item_date, []).append((dt_vn, item))

    results: list[WeatherDay] = []
    # Sắp xếp các ngày tăng dần
    for cur_date in sorted(day_data.keys()):
        m_items = day_data[cur_date]
        if not m_items:
            continue

        rain_by_slot = {"morning": [], "afternoon": [], "evening": []}
        temps_min = []
        temps_max = []
        humidities = []
        is_severe = False
        highest_pop_desc = ""
        highest_pop = -1.0

        for dt_vn, itm in m_items:
            hour = dt_vn.hour
            pop = float(itm.get("pop", 0.0))
            main = itm.get("main", {})
            weather_list = itm.get("weather", [{}])
            w_info = weather_list[0] if weather_list else {}
            w_id = w_info.get("id", 800)
            desc = w_info.get("description", "")
            wind = itm.get("wind", {})
            wind_speed = float(wind.get("speed", 0.0))

            # Gán slot
            if 6 <= hour <= 11:
                rain_by_slot["morning"].append(pop)
            elif 12 <= hour <= 17:
                rain_by_slot["afternoon"].append(pop)
            elif 18 <= hour <= 21:
                rain_by_slot["evening"].append(pop)

            t_min = float(main.get("temp_min", main.get("temp", 20.0)))
            t_max = float(main.get("temp_max", main.get("temp", 25.0)))
            temps_min.append(t_min)
            temps_max.append(t_max)
            if "humidity" in main:
                humidities.append(float(main["humidity"]))

            # Kiểm tra thời tiết nguy hiểm
            if (200 <= w_id <= 299) or (wind_speed >= 17.0):
                is_severe = True

            # Mô tả theo mốc có pop cao nhất
            if pop > highest_pop or not highest_pop_desc:
                highest_pop = pop
                highest_pop_desc = desc

        rain_prob = {
            "morning": max(rain_by_slot["morning"]) if rain_by_slot["morning"] else 0.0,
            "afternoon": max(rain_by_slot["afternoon"]) if rain_by_slot["afternoon"] else 0.0,
            "evening": max(rain_by_slot["evening"]) if rain_by_slot["evening"] else 0.0,
        }

        t_min_final = min(temps_min) if temps_min else 20.0
        t_max_final = max(temps_max) if temps_max else 25.0
        humidity_final = round(sum(humidities) / len(humidities)) if humidities else 75

        results.append(
            WeatherDay(
                date=cur_date,
                temp_min=round(t_min_final, 1),
                temp_max=round(t_max_final, 1),
                humidity=humidity_final,
                rain_prob=rain_prob,
                condition=highest_pop_desc,
                is_severe=is_severe,
            )
        )

    return results


def get_forecast(
    province: str,
    start_date: date,
    days: int,
    *,
    fetch: Callable[[str], dict] = fetch_raw,
    cache_get: Optional[Callable[[str], Optional[tuple[dict, datetime]]]] = None,
    cache_put: Optional[Callable[[str, dict], None]] = None,
    now: Optional[datetime] = None,
) -> list[WeatherDay]:
    """
    Lấy dự báo thời tiết có hỗ trợ bộ nhớ đệm (TTL 3 giờ).
    Nếu cache còn hạn: không gọi fetch.
    """
    curr_now = now or datetime.now()
    raw_data = None

    if cache_get:
        cached = cache_get(province)
        if cached:
            c_data, cached_at = cached
            # Kiểm tra TTL
            if cached_at.tzinfo is not None and curr_now.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=None)
            elif cached_at.tzinfo is None and curr_now.tzinfo is not None:
                curr_now = curr_now.replace(tzinfo=None)

            if cached_at + timedelta(hours=WEATHER_CACHE_TTL_HOURS) > curr_now:
                raw_data = c_data

    if raw_data is None:
        raw_data = fetch(province)
        if cache_put:
            cache_put(province, raw_data)

    return parse_forecast(raw_data, start_date, days)
