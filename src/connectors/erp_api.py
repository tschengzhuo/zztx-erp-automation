"""
ERP API 连接器
封装与 ERP 系统的 HTTP API 交互
"""

import json
from typing import Any, Dict, Optional

import requests

from src.common.exceptions import ERPAPIException
from src.common.logger import get_logger

logger = get_logger(__name__)


class ERPAPIConnector:
    """ERP API 连接器"""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        retry_times: int = 3
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.retry_times = retry_times
        self.session = requests.Session()

        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法 (GET/POST/PUT/DELETE)
            endpoint: API 端点路径
            params: URL 查询参数
            data: 请求体数据

        Returns:
            API 响应的 JSON 数据
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error = None

        for attempt in range(1, self.retry_times + 1):
            try:
                logger.debug(f"[{method}] {url} (attempt {attempt})")
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data,
                    timeout=self.timeout,
                    **kwargs
                )
                response.raise_for_status()
                return response.json()
            except requests.HTTPError as e:
                last_error = ERPAPIException(
                    f"HTTP error: {e}",
                    status_code=e.response.status_code,
                    response_body=e.response.text
                )
                logger.warning(f"HTTP error on attempt {attempt}: {e}")
            except requests.RequestException as e:
                last_error = ERPAPIException(f"Request failed: {e}")
                logger.warning(f"Request failed on attempt {attempt}: {e}")

        logger.error(f"All {self.retry_times} attempts failed for {url}")
        raise last_error

    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """发送 GET 请求"""
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """发送 POST 请求"""
        return self._request("POST", endpoint, data=data)

    def put(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """发送 PUT 请求"""
        return self._request("PUT", endpoint, data=data)

    def delete(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """发送 DELETE 请求"""
        return self._request("DELETE", endpoint, params=params)
