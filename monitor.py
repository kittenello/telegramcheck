import base64
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API = "https://api.github.com"
UPSTREAM = "TelegramMessenger/Telegram-iOS"
STATE_BRANCH = "monitor-state"
STATE_FILE = "telegram-ios-tags.json"


def request(url, token=None, payload=None, method=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "telegram-ios-tag-monitor"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def tags(token):
    found = []
    for page in range(1, 101):
        result = request(f"{API}/repos/{UPSTREAM}/tags?per_page=100&page={page}", token)
        if not isinstance(result, list):
            raise ValueError("неверный ответ github со списком тегов")
        found.extend(item["name"] for item in result if re.fullmatch(r"release-\d+(?:\.\d+)*", item["name"]))
        if len(result) < 100:
            if not found:
                raise ValueError("теги версий не найдены")
            return sorted(set(found))
    raise ValueError("слишком много страниц тегов")


def send(bot_token, chat_id, message):
    url = "https://api.telegram.org/bot" + bot_token + "/sendMessage"
    response = request(url, payload={"chat_id": chat_id, "text": message, "disable_web_page_preview": True})
    if not response.get("ok"):
        raise ValueError("telegram не принял сообщение")


def state_api(repo):
    return f"{API}/repos/{repo}/contents/{STATE_FILE}"


def load_state(repo, token, head):
    try:
        result = request(state_api(repo) + "?ref=" + STATE_BRANCH, token)
    except HTTPError as error:
        if error.code != 404:
            raise
        try:
            request(f"{API}/repos/{repo}/git/ref/heads/{STATE_BRANCH}", token)
        except HTTPError as branch_error:
            if branch_error.code != 404:
                raise
            request(f"{API}/repos/{repo}/git/refs", token, {"ref": "refs/heads/" + STATE_BRANCH, "sha": head})
        return None, None
    raw = base64.b64decode(result["content"])
    data = json.loads(raw)
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("неверный файл состояния")
    return set(data), result["sha"]


def save_state(repo, token, seen, sha):
    content = base64.b64encode((json.dumps(sorted(seen), ensure_ascii=False) + "\n").encode()).decode()
    data = {"message": "chore: update monitored tags", "content": content, "branch": STATE_BRANCH}
    if sha:
        data["sha"] = sha
    result = request(state_api(repo), token, data, method="PUT")
    return result["content"]["sha"]


def run(mode, repo, token, bot_token, chat_id, head):
    if mode == "test":
        send(bot_token, chat_id, "тест: уведомления об обновлениях telegram ios работают.")
        print("тестовое сообщение отправлено")
        return
    if mode != "check":
        raise ValueError("неизвестный режим")
    current = tags(token)
    seen, sha = load_state(repo, token, head)
    if seen is None:
        save_state(repo, token, set(current), None)
        print("текущие теги сохранены, ожидание новых")
        return
    for tag in sorted(set(current) - seen):
        link = f"https://github.com/{UPSTREAM}/releases/tag/{quote(tag, safe='')}"
        send(bot_token, chat_id, f"вышло обновление telegram ios: {tag}\n{link}")
        seen.add(tag)
        sha = save_state(repo, token, seen, sha)
        print("уведомление отправлено: " + tag)
    print("проверка завершена")


def main():
    keys = ("GITHUB_REPOSITORY", "GH_TOKEN", "BOT_TOKEN", "CHAT_ID", "GITHUB_SHA")
    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        raise ValueError("не заданы параметры: " + ", ".join(missing))
    run(os.environ.get("MODE", "check"), *(os.environ[key] for key in keys))


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print(f"ошибка сервиса: http {error.code}", file=sys.stderr)
        sys.exit(1)
    except (URLError, TimeoutError):
        print("ошибка соединения", file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError, TypeError):
        print("ошибка данных или настройки; проверьте секреты и права workflow", file=sys.stderr)
        sys.exit(1)
