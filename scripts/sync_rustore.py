#!/usr/bin/env python3
"""Fill repo.json descriptions, ratings and reviews from RuStore.

Each app keeps IPA / icon / downloadURL locally. Only metadata is pulled
when rustoreURL is set, e.g. https://www.rustore.ru/catalog/app/com.idamob.tinkoff.android
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_JSON = ROOT / "repo.json"

RUSTORE_VER = "12000"
INFO_URL = "https://backapi.rustore.ru/applicationData/overallInfo/{package}"
REVIEWS_URL = "https://www.rustore.ru/catalog/app/{package}/reviews"
JINA = "https://r.jina.ai/"

CTX = ssl.create_default_context()

COMPANY_WEBSITES = {
    "сбербанк": "https://www.sberbank.ru",
    "сбер": "https://www.sberbank.ru",
    "т-банк": "https://www.tbank.ru",
    "тбанк": "https://www.tbank.ru",
    "tbank": "https://www.tbank.ru",
    "tinkoff": "https://www.tbank.ru",
    "альфа": "https://alfabank.ru",
    "втб": "https://www.vtb.ru",
    "газпромбанк": "https://www.gazprombank.ru",
    "мтсбанк": "https://www.mtsbank.ru",
    "псб": "https://www.psbank.ru",
    "россельхоз": "https://www.rshb.ru",
    "совкомбанк": "https://sovcombank.ru",
    "халва": "https://sovcombank.ru",
    "юmoney": "https://yoomoney.ru",
    "юмани": "https://yoomoney.ru",
    "яндекс музыка": "https://music.yandex.ru",
    "яндекс": "https://bank.yandex.ru",
    "rutube": "https://rutube.ru",
    "макс": "https://max.ru",
}

PRIVACY_PAGES = {
    "сбербанк": "https://www.sberbank.ru/privacy",
    "сбер": "https://www.sberbank.ru/privacy",
    "т-банк": "https://www.tbank.ru/privacy/",
    "тбанк": "https://www.tbank.ru/privacy/",
    "tbank": "https://www.tbank.ru/privacy/",
    "tinkoff": "https://www.tbank.ru/privacy/",
    "альфа": "https://alfabank.ru/privacy/",
    "втб": "https://www.vtb.ru/privacy/",
    "газпромбанк": "https://www.gazprombank.ru/privacy/",
    "мтсбанк": "https://www.mtsbank.ru/privacy/",
    "псб": "https://www.psbank.ru/privacy/",
    "россельхоз": "https://www.rshb.ru/privacy/",
    "совкомбанк": "https://sovcombank.ru/privacy/",
    "халва": "https://sovcombank.ru/privacy/",
    "юmoney": "https://yoomoney.ru/page?id=529434",
    "юмани": "https://yoomoney.ru/page?id=529434",
    "яндекс музыка": "https://yandex.ru/legal/confidential/",
    "яндекс": "https://yandex.ru/legal/confidential/",
    "rutube": "https://rutube.ru/info/privacy",
    "макс": "https://max.ru/legal/privacy",
}

PRESERVE = {
    "name",
    "bundleIdentifier",
    "iconURL",
    "tintColor",
    "downloadURL",
    "size",
    "versions",
    "version",
    "versionDate",
    "website",
    "privacyURL",
}

PACKAGE_HINTS = {
    "т-банк": "com.idamob.tinkoff.android",
    "t-bank": "com.idamob.tinkoff.android",
    "tinkoff": "com.idamob.tinkoff.android",
    "сбербанк": "ru.sberbankmobile",
    "сбер": "ru.sberbankmobile",
    "sberbank": "ru.sberbankmobile",
    "альфа": "ru.alfabank.mobile.android",
    "втб": "ru.vtb24.mobilebanking.android",
    "газпромбанк": "ru.gazprombank.android.mobilebank.app",
    "мтс": "ru.lewis.dbo",
    "псб": "logo.com.mbanking",
    "россельхоз": "ru.rshb.dbo",
    "совкомбанк": "ru.sovcomcard.halva.v1",
    "т-инвестиции": "ru.tinkoff.investing",
    "тинвестиции": "ru.tinkoff.investing",
    "юмани": "ru.yoo.money",
    "yumoney": "ru.yoo.money",
    "яндекс музыка": "ru.yandex.music",
    "яндекс": "com.yandex.bank",
    "rutube": "ru.rutube.app",
    "макс": "ru.oneme.app",
}


def request(url: str, headers: dict[str, str] | None = None, timeout: int = 40) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "*/*",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as response:
        return response.read()


def package_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"/catalog/app/([^/?#]+)", url)
    if match:
        return match.group(1)
    return None


def lookup_page(mapping: dict[str, str], app: dict, info: dict | None = None) -> str | None:
    blob = " ".join(
        str(value or "")
        for value in (
            app.get("name"),
            app.get("developerName"),
            (info or {}).get("companyName"),
        )
    ).lower().replace("«", "").replace("»", "").replace(" ", "").replace("-", "")
    for needle, url in sorted(
        mapping.items(),
        key=lambda item: len(item[0].replace(" ", "").replace("-", "")),
        reverse=True,
    ):
        key = needle.replace("-", "").replace(" ", "")
        if key and key in blob:
            return url
    return None


def guessed_package(app: dict) -> str | None:
    blob = " ".join(
        str(app.get(key) or "")
        for key in ("name", "developerName", "bundleIdentifier", "rustoreURL")
    ).lower()
    for needle, package in sorted(PACKAGE_HINTS.items(), key=lambda item: len(item[0]), reverse=True):
        if needle in blob:
            return package
    return None


def rustore_info(package: str) -> dict:
    raw = request(
        INFO_URL.format(package=package),
        headers={
            "Accept": "application/json",
            "ruStoreVerCode": RUSTORE_VER,
        },
        timeout=25,
    )
    payload = json.loads(raw.decode("utf-8"))
    body = payload.get("body") or {}
    if not isinstance(body, dict) or not body:
        raise RuntimeError(f"empty overallInfo for {package}: {payload.get('message')}")
    return body


def rustore_reviews(package: str, limit: int = 8) -> list[dict]:
    markdown = ""
    for url in (
        JINA + REVIEWS_URL.format(package=package),
        REVIEWS_URL.format(package=package),
    ):
        try:
            markdown = request(url, timeout=45).decode("utf-8", "replace")
            if "Markdown Content:" in markdown or "Нравится:" in markdown:
                break
        except (urllib.error.URLError, TimeoutError, ssl.SSLError):
            continue
    return parse_reviews(markdown, limit=limit)


def parse_reviews(markdown: str, limit: int = 8) -> list[dict]:
    if "Markdown Content:" in markdown:
        markdown = markdown.split("Markdown Content:", 1)[1]
    markdown = markdown.replace("\r\n", "\n")
    markdown = re.sub(
        r"\nРазработчик\n.*?(?=\n[^\n]+\s+(?:Изменён\s+)?\d{1,2}\s+[а-яё.]+\s+\d{4}|\Z)",
        "\n",
        markdown,
        flags=re.S | re.I,
    )

    header = re.compile(
        r"(?m)^(?P<author>.+?)\s+(?:Изменён\s+)?(?P<date>\d{1,2}\s+[а-яё.]+\s+\d{4})\s*$"
    )
    matches = list(header.finditer(markdown))
    reviews: list[dict] = []
    skip_authors = {"разработчик", "сначала новые", "сначала полезные"}

    for index, match in enumerate(matches):
        author = match.group("author").strip()
        if author.lower() in skip_authors:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        chunk = markdown[start:end]
        like = re.search(r"Нравится:", chunk)
        text = chunk[: like.start()] if like else chunk
        text = re.sub(r"\[.*?\]\(.*?\)", "", text)
        text = re.sub(r"\n{2,}", "\n", text).strip(" \n-")
        if len(text) < 2:
            continue
        reviews.append(
            {
                "id": f"{author}-{match.group('date')}-{index}",
                "title": review_title(text),
                "author": author,
                "text": text,
                "date": match.group("date"),
            }
        )
        if len(reviews) >= limit:
            break
    return reviews


def review_title(text: str) -> str:
    sentence = re.split(r"(?<=[.!?…])\s+", text.strip(), maxsplit=1)[0].strip()
    if len(sentence) > 46:
        cut = sentence[:44]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return cut
    return sentence


def screenshots(info: dict) -> list[str]:
    files = [
        item
        for item in (info.get("fileUrls") or [])
        if isinstance(item, dict)
        and item.get("type") == "SCREENSHOT"
        and item.get("fileUrl")
    ]
    files.sort(key=lambda item: item.get("ordinal") or 0)
    return [item["fileUrl"] for item in files]


def apply_info(app: dict, info: dict, reviews: list[dict]) -> None:
    rating = info.get("rating") or {}
    if info.get("fullDescription"):
        app["localizedDescription"] = info["fullDescription"].strip()
    if info.get("shortDescription"):
        app["subtitle"] = info["shortDescription"].strip()
    if info.get("companyName"):
        app["developerName"] = info["companyName"]
    categories = info.get("categories") or []
    if categories:
        app["category"] = categories[0]
    elif info.get("category"):
        app["category"] = info["category"]
    if isinstance(rating, dict):
        if rating.get("average") is not None:
            app["rating"] = rating["average"]
        if rating.get("votes") is not None:
            app["ratingCount"] = rating["votes"]
    if info.get("downloads") is not None:
        app["downloads"] = info["downloads"]
    if info.get("roundedDownloadsText"):
        app["downloadsText"] = info["roundedDownloadsText"]
    if info.get("whatsNew"):
        app["versionDescription"] = info["whatsNew"].strip()
        versions = app.get("versions")
        if isinstance(versions, list) and versions:
            versions[0]["localizedDescription"] = info["whatsNew"].strip()
    shots = screenshots(info)
    if shots:
        app["screenshotURLs"] = shots
    age = ((info.get("ageRestriction") or {}) if isinstance(info.get("ageRestriction"), dict) else {}).get("category")
    age = age or info.get("ageLegal")
    if age:
        app["ageRating"] = str(age)
    contacts = info.get("developerContacts") if isinstance(info.get("developerContacts"), dict) else {}
    company_site = lookup_page(COMPANY_WEBSITES, app, info)
    if company_site:
        app["website"] = company_site
    elif not app.get("website"):
        website = (contacts or {}).get("website") or info.get("website")
        if website:
            app["website"] = website
    privacy = lookup_page(PRIVACY_PAGES, app, info)
    if privacy and not app.get("privacyURL"):
        app["privacyURL"] = privacy
    copyright_match = re.search(r"©[^\n]+", info.get("fullDescription") or "")
    if copyright_match:
        app["copyright"] = copyright_match.group(0).strip()
    if reviews:
        app["reviews"] = reviews
    apply_pins(app)


def apply_pins(app: dict) -> None:
    if app.get("pinnedWhatsNew"):
        text = str(app["pinnedWhatsNew"]).strip()
        app["versionDescription"] = text
        versions = app.get("versions")
        if isinstance(versions, list) and versions:
            versions[0]["localizedDescription"] = text
    if app.get("pinnedCategory"):
        app["category"] = app["pinnedCategory"]


def sync_app(app: dict) -> str | None:
    package = package_from_url(app.get("rustoreURL")) or guessed_package(app)
    if not package:
        return None
    if not app.get("rustoreURL"):
        app["rustoreURL"] = f"https://www.rustore.ru/catalog/app/{package}"
    info = rustore_info(package)
    reviews = rustore_reviews(package)
    apply_info(app, info, reviews)
    return package


def main() -> int:
    repo = json.loads(REPO_JSON.read_text(encoding="utf-8"))
    apps = repo.get("apps") or []
    updated = []
    errors = []
    only = {item.casefold() for item in sys.argv[1:]}
    for app in apps:
        name = app.get("name") or app.get("bundleIdentifier")
        if only and not any(item in str(name).casefold() for item in only):
            continue
        try:
            package = sync_app(app)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
            continue
        if package:
            updated.append(f"{name} ({package})")
            print(f"ok {name} <- {package} reviews={len(app.get('reviews') or [])}")
        else:
            print(f"skip {name}: no rustoreURL")

    REPO_JSON.write_text(
        json.dumps(repo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if errors:
        print("errors:", file=sys.stderr)
        for item in errors:
            print(" ", item, file=sys.stderr)
    print(f"updated {len(updated)} apps")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
