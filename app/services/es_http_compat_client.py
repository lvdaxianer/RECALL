"""
Elasticsearch HTTP 兼容客户端

用于兼容 ES 7.10 类服务在新版 Python 客户端产品校验失败时的基础操作。
"""

from typing import Any, Dict, List, Optional

import httpx


class ESHttpCompatIndices:
    """HTTP 兼容客户端的 indices API 子集。"""

    def __init__(self, owner: "ESHttpCompatClient"):
        self._owner = owner

    def exists(self, index: str) -> bool:
        response = self._owner.request("HEAD", f"/{index}")
        return response.status_code == 200

    def create(self, index: str, body: Dict[str, Any]):
        response = self._owner.request("PUT", f"/{index}", json=body)
        response.raise_for_status()
        return response.json()

    def delete(self, index: str, ignore: Optional[List[int]] = None):
        response = self._owner.request("DELETE", f"/{index}")
        if response.status_code in (ignore or []):
            return {"acknowledged": True}
        response.raise_for_status()
        return response.json()

    def refresh(self, index: str):
        response = self._owner.request("POST", f"/{index}/_refresh")
        response.raise_for_status()
        return response.json()

    def analyze(self, body: Dict[str, Any]):
        response = self._owner.request("POST", "/_analyze", json=body)
        response.raise_for_status()
        return response.json()


class ESHttpCompatClient:
    """兼容 ES 7.10 类服务的 HTTP 客户端子集。"""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username or password else None
        self.timeout = timeout
        self.indices = ESHttpCompatIndices(self)

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return httpx.request(
            method,
            f"{self.base_url}{path}",
            auth=self.auth,
            timeout=self.timeout,
            **kwargs
        )

    def ping(self) -> bool:
        try:
            return self.request("GET", "/").status_code == 200
        except httpx.HTTPError:
            return False

    def info(self) -> Dict[str, Any]:
        response = self.request("GET", "/")
        response.raise_for_status()
        return response.json()

    def index(self, index: str, id: str, body: Dict[str, Any]):
        response = self.request("PUT", f"/{index}/_doc/{id}", json=body)
        response.raise_for_status()
        return response.json()

    def search(self, index: str, body: Dict[str, Any]) -> Dict[str, Any]:
        response = self.request("POST", f"/{index}/_search", json=body)
        if response.status_code == 404:
            return {"hits": {"hits": []}}
        response.raise_for_status()
        return response.json()

    def delete(self, index: str, id: str):
        response = self.request("DELETE", f"/{index}/_doc/{id}")
        if response.status_code == 404:
            raise KeyError(id)
        response.raise_for_status()
        return response.json()

    def exists(self, index: str, id: str) -> bool:
        response = self.request("HEAD", f"/{index}/_doc/{id}")
        return response.status_code == 200
