"""
Instagramの最新投稿を取得し、画像をリポジトリに保存、
data/instagram-posts.json を更新するスクリプト。

GitHub Actions (.github/workflows/instagram-sync.yml) から毎日実行される。
手元で試す場合は環境変数を設定して `python scripts/fetch_instagram.py` を実行する。

必要な環境変数:
  IG_ACCESS_TOKEN   Instagramの長期アクセストークン
  IG_USER_ID        InstagramビジネスアカウントのユーザーID
  GH_PAT            GitHub Secretsを書き換えるためのPersonal Access Token（repo scope）
  GITHUB_REPOSITORY "owner/repo" 形式（GitHub Actions実行時は自動で設定される）
"""

import json
import os
import sys
import time
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
IMAGES_DIR = ROOT / "images" / "instagram"
POSTS_JSON = DATA_DIR / "instagram-posts.json"
TOKEN_META_JSON = DATA_DIR / "ig-token-meta.json"

POST_LIMIT = 6
TOKEN_REFRESH_INTERVAL_DAYS = 7  # 60日有効なトークンを7日おきに更新（十分に余裕を持たせる）


def log(msg: str) -> None:
    print(f"[instagram-sync] {msg}", flush=True)


def load_token_meta() -> dict:
    if TOKEN_META_JSON.exists():
        return json.loads(TOKEN_META_JSON.read_text(encoding="utf-8"))
    return {}


def save_token_meta(meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_META_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def should_refresh_token(meta: dict) -> bool:
    last = meta.get("last_refreshed")
    if not last:
        return True
    last_dt = datetime.fromisoformat(last)
    age_days = (datetime.now(timezone.utc) - last_dt).days
    return age_days >= TOKEN_REFRESH_INTERVAL_DAYS


def refresh_access_token(current_token: str) -> str:
    log("refreshing long-lived access token...")
    resp = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
        timeout=30,
    )
    resp.raise_for_status()
    new_token = resp.json()["access_token"]
    log("token refreshed successfully.")
    return new_token


def update_github_secret(repo: str, pat: str, secret_name: str, secret_value: str) -> None:
    from nacl import encoding, public

    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }
    key_resp = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=30,
    )
    key_resp.raise_for_status()
    key_data = key_resp.json()

    public_key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    encrypted_b64 = b64encode(encrypted).decode("utf-8")

    put_resp = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
        headers=headers,
        json={"encrypted_value": encrypted_b64, "key_id": key_data["key_id"]},
        timeout=30,
    )
    put_resp.raise_for_status()
    log(f"GitHub secret '{secret_name}' updated.")


def fetch_media(user_id: str, access_token: str) -> list:
    resp = requests.get(
        f"https://graph.instagram.com/{user_id}/media",
        params={
            "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp",
            "access_token": access_token,
            "limit": POST_LIMIT,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def download_image(url: str, dest_stem: Path) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "image/jpeg")
    ext = ".png" if "png" in content_type else ".jpg"
    dest = dest_stem.with_suffix(ext)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return f"images/instagram/{dest.name}"


def main() -> int:
    access_token = os.environ.get("IG_ACCESS_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    gh_pat = os.environ.get("GH_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")

    if not access_token or not user_id:
        log("IG_ACCESS_TOKEN / IG_USER_ID が未設定です。docs/instagram-setup.md を参照して設定してください。")
        return 1

    meta = load_token_meta()
    if should_refresh_token(meta):
        try:
            access_token = refresh_access_token(access_token)
            if gh_pat and repo:
                update_github_secret(repo, gh_pat, "IG_ACCESS_TOKEN", access_token)
            else:
                log("GH_PAT / GITHUB_REPOSITORY が未設定のため、GitHub Secretsの自動更新はスキップしました。")
            meta["last_refreshed"] = datetime.now(timezone.utc).isoformat()
            save_token_meta(meta)
        except requests.HTTPError as e:
            log(f"トークンの更新に失敗しました: {e}. 既存トークンで続行します。")

    try:
        media_items = fetch_media(user_id, access_token)
    except requests.HTTPError as e:
        log(f"投稿の取得に失敗しました: {e}")
        return 1

    posts = []
    for item in media_items:
        image_source = item.get("thumbnail_url") or item.get("media_url")
        if not image_source:
            continue
        try:
            local_path = download_image(image_source, IMAGES_DIR / item["id"])
        except requests.HTTPError as e:
            log(f"画像のダウンロードに失敗しました ({item['id']}): {e}")
            continue

        caption = (item.get("caption") or "").strip()
        posts.append(
            {
                "id": item["id"],
                "caption": caption[:120],
                "permalink": item.get("permalink", ""),
                "image": local_path,
                "timestamp": item.get("timestamp", ""),
            }
        )
        time.sleep(0.3)  # レート制限に配慮

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POSTS_JSON.write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "posts": posts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"{len(posts)}件の投稿を保存しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
