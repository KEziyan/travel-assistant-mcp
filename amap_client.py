import json
import math
import time
import requests


class AmapMCPClient:
    BASE_URL = "https://mcp.amap.com/mcp"

    def __init__(self, api_key):
        self.api_key = api_key

    def _call_tool(self, name, args):
        url = f"{self.BASE_URL}?key={self.api_key}"
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        content_type = resp.headers.get("Content-Type", "")
        if "text/event-stream" in content_type:
            return self._parse_sse(resp.text)
        raw = resp.json()
        error = raw.get("error")
        if error:
            raise RuntimeError(f"MCP error: {error.get('message', str(error))}")
        result = raw.get("result", raw)
        content = result.get("content", [])
        if content and isinstance(content, list) and content[0].get("type") == "text":
            text = content[0]["text"]
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {}
            return {}
        return result

    def _parse_sse(self, text):
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("data:"):
                json_str = stripped[5:].strip()
                if json_str:
                    parsed = json.loads(json_str)
                    result = parsed.get("result", parsed)
                    content = result.get("content", [])
                    if content and isinstance(content, list) and content[0].get("type") == "text":
                        return json.loads(content[0]["text"])
                    return result
        return None

    def geocode(self, city):
        result = self._call_tool("maps_geo", {"address": city, "city": city})
        return self._parse_geocode(result)

    def search_poi(self, keyword, city=None):
        params = {"keywords": keyword}
        if city:
            params["city"] = city
        result = self._call_tool("maps_text_search", params)
        return self._parse_poi_list(result)

    def search_nearby(self, keyword, location, radius=None):
        params = {"keywords": keyword, "location": location}
        if radius:
            params["radius"] = str(radius)
        result = self._call_tool("maps_around_search", params)
        return self._parse_poi_list(result)

    def search_detail(self, poi_id):
        result = self._call_tool("maps_search_detail", {"id": poi_id})
        return self._parse_poi_detail(result)

    def weather(self, city):
        result = self._call_tool("maps_weather", {"city": city})
        return self._parse_weather(result)

    @staticmethod
    def _parse_geocode(data):
        if not data:
            return None
        results = data.get("results") or []
        if isinstance(results, list) and results:
            loc_str = results[0].get("location", "")
            if loc_str:
                lng, lat = loc_str.split(",")
                return {"lng": float(lng), "lat": float(lat), "formatted": loc_str}
        return None

    @staticmethod
    def _parse_poi_list(data):
        if not data:
            return []
        pois = data.get("pois") or []
        if isinstance(pois, list):
            return [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "address": p.get("address", ""),
                    "type": p.get("type", ""),
                    "typecode": p.get("typecode", ""),
                    "photo": p.get("photo", ""),
                }
                for p in pois
                if p.get("id")
            ]
        return []

    @staticmethod
    def _parse_poi_detail(data):
        if not data:
            return None
        poi = data.get("poi") or data
        if isinstance(poi, list) and poi:
            poi = poi[0]
        loc_str = poi.get("location", "")
        lng = lat = None
        if loc_str:
            parts = loc_str.split(",")
            if len(parts) == 2:
                lng, lat = float(parts[0]), float(parts[1])
        return {
            "id": poi.get("id"),
            "name": poi.get("name"),
            "address": poi.get("address", ""),
            "location": loc_str,
            "lng": lng,
            "lat": lat,
            "type": poi.get("type", ""),
            "typecode": poi.get("typecode", ""),
            "photo": poi.get("photo", ""),
            "rating": poi.get("rating", ""),
        }

    @staticmethod
    def _parse_weather(data):
        if not data:
            return []
        forecasts = data.get("forecasts") or []
        if not forecasts and isinstance(data, list):
            forecasts = data
        results = []
        for f in forecasts:
            if "casts" in f:
                for c in f["casts"]:
                    results.append({
                        "date": c.get("date", ""),
                        "week": c.get("week", ""),
                        "dayweather": c.get("dayweather", ""),
                        "nightweather": c.get("nightweather", ""),
                        "daytemp": c.get("daytemp", ""),
                        "nighttemp": c.get("nighttemp", ""),
                        "daywind": c.get("daywind", ""),
                        "nightwind": c.get("nightwind", ""),
                    })
            else:
                results.append({
                    "date": f.get("date", ""),
                    "week": f.get("week", ""),
                    "dayweather": f.get("dayweather", ""),
                    "nightweather": f.get("nightweather", ""),
                    "daytemp": f.get("daytemp", ""),
                    "nighttemp": f.get("nighttemp", ""),
                    "daywind": f.get("daywind", ""),
                    "nightwind": f.get("nightwind", ""),
                })
        return results


def haversine(loc1, loc2):
    lat1, lon1 = math.radians(loc1[0]), math.radians(loc1[1])
    lat2, lon2 = math.radians(loc2[0]), math.radians(loc2[1])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return 6371 * c


def greedy_tsp(pois, start_location):
    if not pois:
        return []
    if len(pois) == 1:
        p = pois[0]
        dist = haversine(start_location, (p["lat"], p["lng"]))
        p["distance_to_prev"] = round(dist, 2)
        p["travel_time"] = round(dist / 30 * 60, 1)
        return pois

    sorted_pois = []
    remaining = list(pois)
    current = start_location

    while remaining:
        nearest = None
        nearest_dist = float("inf")
        for poi in remaining:
            d = haversine(current, (poi["lat"], poi["lng"]))
            if d < nearest_dist:
                nearest_dist = d
                nearest = poi
        nearest["distance_to_prev"] = round(nearest_dist, 2)
        nearest["travel_time"] = round(nearest_dist / 30 * 60, 1)
        sorted_pois.append(nearest)
        remaining.remove(nearest)
        current = (nearest["lat"], nearest["lng"])

    sorted_pois[0]["distance_to_prev"] = 0
    sorted_pois[0]["travel_time"] = 0
    return sorted_pois
