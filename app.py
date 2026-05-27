import math
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from amap_client import AmapMCPClient, greedy_tsp, haversine

app = Flask(__name__)

ATTRACTION_KEYWORDS = [
    "旅游景点", "风景名胜", "景区", "名胜古迹", "公园", "博物馆", "纪念馆",
    "古镇", "寺庙", "湖泊", "山", "景点", "旅游", "风景区", "文化遗址",
    "历史建筑", "宗教场所", "广场", "游乐场", "温泉", "湿地",
]

FOOD_KEYWORDS = ["特色美食", "当地小吃", "餐厅", "美食"]
HOTEL_KEYWORDS = ["酒店", "宾馆", "住宿"]


@app.route("/")
def index():
    return render_template("index.html")


def _validate_params(data):
    api_key = str(data.get("api_key", "")).strip()
    city = str(data.get("city", "")).strip()
    days_str = str(data.get("days", "")).strip()
    spots_str = str(data.get("spots_per_day", "")).strip()
    start_date_str = str(data.get("start_date", "")).strip()

    if not api_key:
        return None, "请输入高德API Key"
    if not city:
        return None, "请输入目的地城市"

    try:
        days = int(days_str)
    except (ValueError, TypeError):
        return None, "出行天数必须为数字"
    if days < 1 or days > 7:
        return None, "出行天数必须在1-7之间"

    try:
        spots_per_day = int(spots_str)
    except (ValueError, TypeError):
        return None, "每天景点数必须为数字"
    if spots_per_day < 1 or spots_per_day > 3:
        return None, "每天景点数必须在1-3之间"

    start_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            return None, "日期格式错误，请使用YYYY-MM-DD"

    return {
        "api_key": api_key,
        "city": city,
        "days": days,
        "spots_per_day": spots_per_day,
        "start_date": start_date,
        "start_date_str": start_date_str,
    }, None


def _filter_weather(raw_weather, start_date, days):
    if not raw_weather:
        return []
    if not start_date:
        return raw_weather[:days]

    cutoff = start_date.strftime("%Y-%m-%d")
    available = [w for w in raw_weather if w.get("date", "") >= cutoff]

    if not available:
        available = [raw_weather[-1]]

    result = []
    for i in range(days):
        if i < len(available):
            item = dict(available[i])
        else:
            item = dict(available[-1])
        trip_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        item["date"] = trip_date
        result.append(item)

    return result


def _search_food_hotel(client, keywords, location, city, radius=8000, limit=5):
    seen = set()
    candidates = []
    for kw in keywords:
        pois = client.search_nearby(kw, location, radius)
        for p in pois:
            pid = p["id"]
            if pid in seen:
                continue
            seen.add(pid)
            candidates.append(p)

    valid = []
    for c in candidates:
        try:
            detail = client.search_detail(c["id"])
            if detail and detail.get("photo") and detail.get("rating"):
                valid.append(detail)
                if len(valid) >= limit:
                    break
        except Exception:
            pass

    return valid[:limit]


def _build_time_schedule(sorted_pois):
    schedule = []
    current = datetime(2000, 1, 1, 8, 30)

    for i, poi in enumerate(sorted_pois):
        visit_hours = 2.0 if i % 2 == 0 else 2.5
        visit_start = current.strftime("%H:%M")
        current += timedelta(hours=visit_hours)
        visit_end = current.strftime("%H:%M")

        travel_min = poi.get("travel_time", 0)
        taxi_fee = max(8, round(poi.get("distance_to_prev", 0) * 3))

        schedule.append({
            "visit_time": f"{visit_start}-{visit_end}",
            "travel_min": travel_min,
            "taxi_fee": taxi_fee,
        })

        current += timedelta(minutes=travel_min)

    return schedule


def _build_day_map_url(sorted_pois, day_start, day, prev_last=None):
    if not sorted_pois:
        return ""

    if day == 0:
        from_lng, from_lat = day_start[1], day_start[0]
        from_name = "市中心"
    else:
        from_lng, from_lat = prev_last["lng"], prev_last["lat"]
        from_name = prev_last["name"]

    last = sorted_pois[-1]
    to_lng, to_lat = last["lng"], last["lat"]
    to_name = last["name"]

    via_parts = []
    for poi in sorted_pois:
        via_parts.append(f"{poi['lng']},{poi['lat']},{poi['name']}")

    url = (
        f"https://uri.amap.com/navigation"
        f"?from={from_lng},{from_lat},{from_name}"
        f"&to={to_lng},{to_lat},{to_name}"
        f"&via={'|'.join(via_parts)}"
        f"&mode=car&callnative=0&src=城市旅行攻略&policy=0"
    )
    return url


def _generate_travel_tips(weather):
    tips = []

    has_rain = any(
        ("雨" in w.get("dayweather", "") or "雪" in w.get("dayweather", "")
         or "雨" in w.get("nightweather", "") or "雪" in w.get("nightweather", ""))
        for w in weather
    )
    if has_rain:
        tips.append("🧳 行程中有雨雪天气，建议携带雨具")

    max_temp = None
    for w in weather:
        try:
            t = int(w.get("daytemp", 0))
            if max_temp is None or t > max_temp:
                max_temp = t
        except (ValueError, TypeError):
            pass
    if max_temp is not None:
        if max_temp >= 35:
            tips.append(f"🌡 最高气温{max_temp}°C，注意防暑降温，建议多补充水分")
        elif max_temp >= 30:
            tips.append(f"🌡 最高气温{max_temp}°C，天气较热，建议做好防晒")

    min_temp = None
    for w in weather:
        try:
            t = int(w.get("nighttemp", 0))
            if min_temp is None or t < min_temp:
                min_temp = t
        except (ValueError, TypeError):
            pass
    if min_temp is not None and min_temp <= 0:
        tips.append(f"🥶 最低气温{min_temp}°C，注意保暖防寒")

    if not tips:
        tips.append("✅ 天气状况良好，适合出行")

    return tips


def _build_daily_plans(detailed_pois, days, spots_per_day, actual_days, start_date, location, weather):
    daily_plans = []
    center = (location["lat"], location["lng"])
    weather_by_date = {w["date"]: w for w in weather if w.get("date")}

    for day in range(actual_days):
        day_pois = detailed_pois[day * spots_per_day: (day + 1) * spots_per_day]
        if not day_pois:
            break

        day_start = center
        prev_last = None
        if day > 0 and daily_plans:
            prev_last = daily_plans[-1]["attractions"][-1]
            day_start = (prev_last["lat"], prev_last["lng"])

        sorted_pois = greedy_tsp(day_pois, day_start)
        schedule = _build_time_schedule(sorted_pois)

        date_str = ""
        if start_date:
            d = start_date + timedelta(days=day)
            date_str = d.strftime("%Y-%m-%d")

        weather_info = weather_by_date.get(date_str, {})

        attractions = []
        for i, poi in enumerate(sorted_pois):
            attractions.append({
                "name": poi["name"],
                "address": poi.get("address", ""),
                "lng": poi["lng"],
                "lat": poi["lat"],
                "photo": poi.get("photo", ""),
                "distance_to_prev": poi.get("distance_to_prev", 0),
                "travel_time": poi.get("travel_time", 0),
                "visit_time": schedule[i]["visit_time"],
                "travel_min": schedule[i]["travel_min"],
                "taxi_fee": schedule[i]["taxi_fee"],
            })

        map_url = _build_day_map_url(sorted_pois, day_start, day, prev_last)

        daily_plans.append({
            "day": day + 1,
            "date": date_str,
            "weather": weather_info,
            "attractions": attractions,
            "map_url": map_url,
        })

    return daily_plans


@app.route("/test_key", methods=["POST"])
def test_key():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "message": "请求数据为空"})
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"ok": False, "message": "请输入API Key"})
    client = AmapMCPClient(api_key)
    try:
        result = client.geocode("北京")
        if result:
            return jsonify({"ok": True, "message": "Key 有效"})
        return jsonify({"ok": False, "message": "Key 无效或请求失败"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"请求异常：{str(e)}"})


@app.route("/api/plan", methods=["POST"])
def generate_plan():
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求数据为空"}), 400

    params, err = _validate_params(data)
    if err:
        return jsonify({"error": err}), 400

    api_key = params["api_key"]
    city = params["city"]
    days = params["days"]
    spots_per_day = params["spots_per_day"]
    start_date = params["start_date"]
    start_date_str = params["start_date_str"]

    client = AmapMCPClient(api_key)

    location = client.geocode(city)
    if not location:
        return jsonify({"error": f"无法获取城市「{city}」的坐标"}), 500

    raw_weather = client.weather(city) or []
    weather = _filter_weather(raw_weather, start_date, days)

    seen_ids = set()
    need_detail_list = []
    for kw in ATTRACTION_KEYWORDS:
        try:
            pois = client.search_nearby(kw, location["formatted"], 50000)
            for p in pois:
                if p["id"] in seen_ids:
                    continue
                seen_ids.add(p["id"])
                need_detail_list.append(p)
        except Exception:
            pass

    detailed_pois = []
    for poi in need_detail_list:
        try:
            detail = client.search_detail(poi["id"])
            if detail and detail.get("lng") is not None and detail.get("lat") is not None:
                detailed_pois.append(detail)
        except Exception:
            pass

    if not detailed_pois:
        return jsonify({"error": "无法获取景点坐标详情，请检查API Key是否有效"}), 500

    actual_days = min(days, max(1, math.ceil(len(detailed_pois) / spots_per_day)))

    food_recommendations = _search_food_hotel(client, FOOD_KEYWORDS, location["formatted"], city, 8000, 5)
    hotel_recommendations = _search_food_hotel(client, HOTEL_KEYWORDS, location["formatted"], city, 8000, 5)

    daily_plans = _build_daily_plans(
        detailed_pois, days, spots_per_day, actual_days,
        start_date, location, weather,
    )

    travel_tips = _generate_travel_tips(weather)

    return jsonify({
        "city": city,
        "weather": weather,
        "daily_plans": daily_plans,
        "food_recommendations": food_recommendations,
        "hotel_recommendations": hotel_recommendations,
        "travel_tips": travel_tips,
        "actual_days": actual_days,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
