"""Provider profiles and text APIs for the local Fieldweave workbench."""

from dataclasses import dataclass, field, replace
import http.client
import ipaddress
import json
import os
import re
import socket
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ask import EFFORTS, MODEL, MODELS


@dataclass(frozen=True)
class Provider:
    label: str
    base_url: str
    model: str
    env: str = ""
    efforts: tuple = ("none", "low", "medium", "high")


PROVIDERS = {
    "deepseek": Provider("DeepSeek", "https://api.deepseek.com", MODEL, "DEEPSEEK_API_KEY", EFFORTS),
    "openai": Provider("OpenAI", "https://api.openai.com/v1", "gpt-5-mini", "OPENAI_API_KEY"),
    "anthropic": Provider("Claude", "https://api.anthropic.com/v1", "claude-sonnet-5-5", "ANTHROPIC_API_KEY"),
    "gemini": Provider("Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-4-hydrogen", "GEMINI_API_KEY"),
    "compatible": Provider("兼容接口", "", "", efforts=("none",)),
}
MAX_RESPONSE = 2 * 1024 * 1024
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,119}")
HOST = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")
PATH = re.compile(r"(?:/[A-Za-z0-9_.~-]+)*/?")
ERROR_MESSAGES = {
    400: "请检查模型编号和思考强度是否受接口支持",
    401: "请检查 API Key 是否有效",
    402: "请检查供应商账户余额",
    403: "请检查密钥是否有权限访问该模型",
    404: "请核对模型 ID 或接口地址",
    429: "请求达到速率或额度限制，请稍后重试",
}


class ModelError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(RejectRedirects())


@dataclass(frozen=True)
class Profile:
    provider: str
    model: str
    effort: str
    base_url: str
    key: str = field(repr=False)
    environment_key: bool = False

    def public(self):
        provider = PROVIDERS[self.provider]
        return {
            "id": self.provider, "label": provider.label, "model": self.model,
            "effort": self.effort, "efforts": provider.efforts, "base_url": self.base_url,
            "has_key": bool(self.key), "using_environment_key": self.environment_key,
            "choices": MODELS if self.provider == "deepseek" else (),
        }


def base_url(value):
    if not isinstance(value, str) or len(value) > 300:
        raise ModelError(400, "请填写有效的 HTTPS Base URL")
    try:
        url = urlsplit(value.strip())
        valid = (
            url.scheme == "https" and url.hostname and HOST.fullmatch(url.hostname)
            and url.port in (None, 443) and url.netloc.lower() in (url.hostname, url.hostname + ":443")
            and not url.query and not url.fragment and PATH.fullmatch(url.path)
            and all(part not in (".", "..") for part in url.path.split("/"))
        )
    except ValueError:
        valid = False
    if not valid:
        raise ModelError(400, "请填写公开的 HTTPS Base URL，例如 https://api.example.com/v1")
    path = url.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[:-len("/chat/completions")]
    return "https://" + url.hostname + path


class PublicHTTPSConnection(http.client.HTTPSConnection):
    """Resolve once, exclude private targets, and retain hostname verification."""

    def connect(self):
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
        if not ips or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in ips):
            raise ModelError(400, "自定义接口需要可公开访问的 HTTPS 域名")
        last_error = None
        for family, kind, protocol, _, address in addresses:
            sock = socket.socket(family, kind, protocol)
            try:
                sock.settimeout(self.timeout)
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as error:
                sock.close()
                last_error = error
        raise last_error


def request_json(profile, path, payload=None, *, timeout=12):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if profile.provider == "anthropic":
        headers.update({"x-api-key": profile.key, "anthropic-version": "2023-06-01"})
    else:
        headers["Authorization"] = "Bearer " + profile.key
    if data is not None:
        headers["Content-Type"] = "application/json"
    status = None
    try:
        if profile.provider == "compatible":
            endpoint = urlsplit(profile.base_url)
            conn = PublicHTTPSConnection(endpoint.hostname, timeout=timeout)
            try:
                conn.request("POST" if data is not None else "GET", endpoint.path + path, body=data, headers=headers)
                response = conn.getresponse()
                status = response.status
                raw = response.read(MAX_RESPONSE + 1) if status == 200 else b""
            finally:
                conn.close()
        else:
            request = Request(profile.base_url + path, data=data, headers=headers)
            with OPENER.open(request, timeout=timeout) as response:
                status = response.status
                raw = response.read(MAX_RESPONSE + 1) if status == 200 else b""
    except HTTPError as error:
        status = error.code
        raw = b""
        error.close()
    except (OSError, http.client.HTTPException) as error:
        raise ModelError(502, "暂时无法连接模型接口，请检查网络") from error
    if status != 200:
        public_status = 422 if 400 <= status < 500 else 502
        raise ModelError(public_status, ERROR_MESSAGES.get(status, "模型服务暂不可用"))
    if len(raw) > MAX_RESPONSE:
        raise ModelError(502, "模型返回内容超过本地处理上限")
    try:
        return json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ModelError(502, "模型接口没有返回可读的 JSON") from error


def generate(profile, system, content):
    provider = profile.provider
    default_tokens = 2048 if provider in {"deepseek", "compatible"} else 8192
    tokens = {"none": default_tokens, "low": 4096, "medium": 6144, "high": 8192, "max": 8192}[profile.effort]
    payload = {"model": profile.model, "messages": [{"role": "user", "content": content}]}
    if provider == "anthropic":
        payload.update(system=system, max_tokens=tokens)
        if profile.effort != "none":
            payload["thinking"] = {"type": "adaptive"}
            payload["output_config"] = {"effort": profile.effort}
        path = "/messages"
    else:
        payload["messages"].insert(0, {"role": "system", "content": system})
        payload["max_completion_tokens" if provider == "openai" else "max_tokens"] = tokens
        if provider == "deepseek" or profile.effort != "none":
            payload["reasoning_effort"] = profile.effort
        path = "/chat/completions"
    result = request_json(profile, path, payload, timeout=100 if profile.effort == "none" else 150)
    try:
        if provider == "anthropic":
            blocks = result["content"]
            answer = "\n".join(
                block["text"] for block in blocks
                if block.get("type") == "text" and isinstance(block.get("text"), str))
            thinking = "\n".join(
                block["thinking"] for block in blocks
                if block.get("type") == "thinking" and isinstance(block.get("thinking"), str))
        else:
            message = result["choices"][0]["message"]
            answer = message.get("content")
            thinking = message.get("reasoning_content") or message.get("reasoning") or ""
            if isinstance(thinking, list):
                thinking = "\n".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in thinking)
            if not isinstance(thinking, str):
                thinking = ""
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("empty answer")
    except (TypeError, ValueError, KeyError, IndexError, AttributeError) as error:
        raise ModelError(502, "模型接口未返回可用的文本回答") from error
    return answer.strip(), thinking.strip()


def verify(profile):
    if profile.provider == "compatible":
        result = request_json(profile, "/chat/completions", {
            "model": profile.model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 32,
        })
        if not isinstance(result, dict) or not result.get("choices"):
            raise ModelError(502, "接口没有返回兼容的测试回答")
        return
    named = profile.provider in {"anthropic", "openai"}
    path = "/models/" + quote(profile.model, safe="") if named else "/models"
    result = request_json(profile, path)
    if named:
        available = isinstance(result, dict) and isinstance(result.get("id"), str)
    else:
        records = result.get("data") if isinstance(result, dict) else None
        available = isinstance(records, list) and any(
            isinstance(item, dict) and item.get("id") == profile.model for item in records
        )
    if not available:
        raise ModelError(422, "接口已响应，但模型未出现在可用列表中，请核对模型 ID")


class ModelSettings:
    def __init__(self, environment_key=None):
        self.lock = Lock()
        self.profiles = {}
        for name, provider in PROVIDERS.items():
            key = os.environ.get(provider.env, "").strip() if provider.env else ""
            if name == "deepseek" and environment_key is not None:
                key = environment_key
            self.profiles[name] = Profile(name, provider.model, "none", provider.base_url, key, bool(key))
        self.active = "deepseek" if self.profiles["deepseek"].key else "local"

    def snapshot(self):
        with self.lock:
            return self.profiles.get(self.active)

    def status(self):
        with self.lock:
            current = self.profiles.get(self.active)
            return {
                "active": self.active, "enabled": current is not None,
                "profiles": [profile.public() for profile in self.profiles.values()],
            }

    def profile_from_input(self, name, payload):
        saved = self.profiles[name]
        model = payload.get("model", saved.model)
        effort = payload.get("effort", saved.effort)
        key = payload.get("key", "")
        if not isinstance(model, str) or not MODEL_ID.fullmatch(model.strip()):
            raise ModelError(400, "请填写有效的模型 ID")
        if effort not in PROVIDERS[name].efforts:
            raise ModelError(400, "请选择此接口支持的思考强度")
        if not isinstance(key, str) or (key.strip() and not re.fullmatch(r"[!-~]{1,1000}", key.strip())):
            raise ModelError(400, "API Key 格式不正确")
        url = base_url(payload.get("base_url", saved.base_url)) if name == "compatible" else saved.base_url
        new_key = key.strip()
        if not new_key and saved.base_url != url:
            raise ModelError(400, "接口地址已变更，请填写新地址对应的密钥")
        if not (new_key or saved.key):
            raise ModelError(400, "请填写这个供应商的 API Key")
        return Profile(name, model.strip(), effort, url, new_key or saved.key, not new_key and saved.environment_key)

    def configure(self, payload, *, test=False):
        if not isinstance(payload, dict):
            raise ModelError(400, "请选择要配置的供应商")
        name = payload.get("provider")
        action = payload.get("action", "save")
        with self.lock:
            if not test and name == "local" and action == "select":
                self.active = "local"
                profile = None
            elif not isinstance(name, str) or name not in PROVIDERS:
                raise ModelError(400, "请选择要配置的供应商")
            elif not test and action == "clear":
                self.profiles[name] = replace(self.profiles[name], key="", environment_key=False)
                if self.active == name:
                    self.active = "local"
                profile = None
            elif action in ("save", "select"):
                profile = self.profile_from_input(name, payload)
                if not test:
                    self.profiles[name] = profile
                    self.active = name
            else:
                raise ModelError(400, "无法识别模型配置操作")
        if test:
            verify(profile)
            return {"verified": True, "provider": name, "model": profile.model}
        return self.status()
