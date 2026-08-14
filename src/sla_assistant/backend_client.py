import json
from urllib.request import urlopen


class HttpBackendClient:
    def __init__(self, api_url: str) -> None:
        self._api_url = api_url.rstrip("/")

    def is_ready(self) -> bool:
        with urlopen(f"{self._api_url}/health/ready", timeout=5) as response:
            payload: object = json.load(response)
        return response.status == 200 and payload == {"status": "ready"}
