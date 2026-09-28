"""喜马拉雅开放平台免费点播内容 API 采集器。

每月自动执行的用户流程：
读取儿童元数据树 → 找到当前平台存在的年龄段选项 → 优先 0-1 岁，没有则取 0-3 岁
→ 再按儿歌/哄睡等内容属性取热门榜 → 自动标记「平台精确年龄段」或「内容属性推断」。

实测备注（2026-09，真实凭据验证）：开放 API 的儿童分类当前不下发内容
（/v2/metadata/albums 对儿童分类 total=0，与元数据树 openapiContentsNum=0 一致），
采集结果为空时由 collector 回退到网页采集路径，本模块如实返回空列表。
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE_URL = "https://api.ximalaya.com"
DEVICE_ID = "6f0f2c1a8f9b4d0e"  # 服务端不校验注册，仅需稳定标识
CHILD_CATEGORY_NAME = "儿童"
# 年龄段优先级：精确 0-1 岁，回退 0-3 岁；均不存在则按内容属性推断。
AGE_PREFERENCES = ("0-1岁", "0-3岁")
# 内容属性按此优先级取热门榜。
CONTENT_ATTRIBUTE_KEYWORDS = ("儿歌", "哄睡", "白噪音", "轻音乐", "安眠曲", "童谣")
HOTTEST = "1"  # calc_dimension: 1-热门推荐 2-最新 3-最多播放
MAX_ALBUMS_PER_ATTRIBUTE = 10
RATE_LIMIT_ERROR_NO = 104


class CredentialsMissing(Exception):
    """未配置 XM_APP_KEY / XM_APP_SECRET 环境变量。"""


class XimalayaApiError(Exception):
    """开放平台返回错误或网络失败。"""

    def __init__(self, message: str, error_no: int | None = None):
        super().__init__(message)
        self.error_no = error_no


def sign(params: dict[str, str], app_secret: str) -> str:
    """官方签名：参数按 key 排序 k=v& 拼接 → UTF-8 Base64 → HMAC-SHA1（原始字节）→ MD5 小写。"""
    base = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    b64 = base64.b64encode(base.encode("utf-8"))
    digest = hmac.new(app_secret.encode("utf-8"), b64, hashlib.sha1).digest()
    return hashlib.md5(digest).hexdigest()


class XimalayaClient:
    def __init__(self, app_key: str, app_secret: str, base_url: str = BASE_URL):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url

    @classmethod
    def from_env(cls) -> "XimalayaClient":
        app_key, app_secret = os.getenv("XM_APP_KEY"), os.getenv("XM_APP_SECRET")
        if not app_key or not app_secret:
            raise CredentialsMissing("需要环境变量 XM_APP_KEY 与 XM_APP_SECRET")
        return cls(app_key, app_secret)

    def get(self, path: str, **business_params: str) -> object:
        params = {
            "app_key": self.app_key,
            "timestamp": str(int(time.time() * 1000)),
            "client_os_type": "4",  # 4 = Linux/服务端
            "nonce": uuid.uuid4().hex,
            "device_id": DEVICE_ID,
            "device_id_type": "UUID",
            "server_api_version": "1.0.0",
        }
        params.update(business_params)
        params["sig"] = sign(params, self.app_secret)
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        for attempt in range(2):
            try:
                return self._request_json(url)
            except XimalayaApiError as exc:
                # 月度任务无人值守：限流时退避一次重试，其余错误直接抛出。
                if attempt == 0 and exc.error_no == RATE_LIMIT_ERROR_NO:
                    time.sleep(30)
                    continue
                raise

    def _request_json(self, url: str) -> object:
        request = urllib.request.Request(url, headers={"User-Agent": "KidsCatalog/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            raise XimalayaApiError(
                f"{url.split('?')[0]} HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}",
                error_no=None) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise XimalayaApiError(f"请求开放平台失败: {exc}") from exc


def _flatten_attributes(metadata: list) -> list[dict]:
    """把元数据树拉平为 [{owner_id, value}]，owner_id 是该属性所属元数据层的 id。"""
    flat: list[dict] = []

    def walk(node: dict) -> None:
        for attr in node.get("attributes", []):
            flat.append({"owner_id": str(node["id"]), "value": str(attr["attr_value"]),
                         "display_name": str(attr.get("display_name") or attr["attr_value"])})
            for child in attr.get("child_metadatas") or []:
                walk(child)

    for node in metadata:
        walk(node)
    return flat


def pick_age(attributes: list[dict]) -> dict | None:
    """按 AGE_PREFERENCES 优先级匹配年龄属性；匹配时容许 0-1/0~1/0–1 等写法。"""
    def normalized(value: str) -> str:
        return re.sub(r"[-~～–—]|岁|\s+", "", value)

    for preference in AGE_PREFERENCES:
        target = normalized(preference)
        for attr in attributes:
            if target in (normalized(attr["value"]), normalized(attr["display_name"])):
                return attr
    return None


def pick_content_attributes(attributes: list[dict]) -> list[dict]:
    picked = []
    for keyword in CONTENT_ATTRIBUTE_KEYWORDS:
        for attr in attributes:
            if keyword in attr["value"] or keyword in attr["display_name"]:
                picked.append(attr)
                break
    return picked


def collect_ximalaya_official(client: XimalayaClient) -> list[dict]:
    """按用户流程采集儿童热门专辑；开放平台无儿童内容时返回空列表。"""
    categories = client.get("/categories/list")
    child = next((c for c in categories if c.get("category_name") == CHILD_CATEGORY_NAME), None)
    if not child:
        raise XimalayaApiError(f"开放平台分类列表中没有「{CHILD_CATEGORY_NAME}」分类")

    attributes = _flatten_attributes(
        client.get("/v2/metadata/list", category_id=str(child["id"])))
    age = pick_age(attributes)
    contents = pick_content_attributes(attributes)
    if not contents:
        return []

    rows: list[dict] = []
    seen: set[str] = set()
    for content in contents:
        filters = [f"{content['owner_id']}:{content['value']}"]
        if age:
            filters.append(f"{age['owner_id']}:{age['value']}")
        result = client.get("/v2/metadata/albums", category_id=str(child["id"]),
                            metadata_attributes=";".join(filters),
                            calc_dimension=HOTTEST, count=str(MAX_ALBUMS_PER_ATTRIBUTE))
        for album in result.get("albums", []):
            album_id = str(album["id"])
            if album_id in seen:
                continue
            seen.add(album_id)
            if age:
                evidence = f"平台元数据精确年龄段 {age['display_name']}；内容属性 {content['display_name']}"
                confidence = "高"
            else:
                evidence = (f"平台无 {'/'.join(AGE_PREFERENCES)} 岁年龄段元数据，"
                            f"由内容属性 {content['display_name']} 推断")
                confidence = "中"
            rows.append({
                "platform": "喜马拉雅开放平台", "album_id": album_id,
                "title": album["album_title"],
                "url": f"https://www.ximalaya.com/album/{album_id}",
                "age_evidence": evidence, "age_confidence": confidence,
                # is_paid 缺失时保持 None，前端显示「付费未知」而非猜测。
                "sale_type": {True: 1, False: 0}.get(album.get("is_paid")),
            })
    return rows
