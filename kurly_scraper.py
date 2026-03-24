#!/usr/bin/env python3
"""
Kurly 카테고리 상품 스크래퍼
- 상품명, 원문링크, 가격을 CSV로 저장
- headless 모드 선택 가능
- 수집할 페이지 수 입력 가능

사용법:
    pip install playwright beautifulsoup4
    playwright install chromium
    python kurly_scraper.py
"""

import csv
import re
import time
from datetime import datetime

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


BASE_URL = "https://www.kurly.com"
CATEGORY_URL = "https://www.kurly.com/categories/910001"


def scrape_page(page, page_num: int) -> list[dict]:
    """단일 페이지에서 상품 정보를 파싱합니다."""
    url = f"{CATEGORY_URL}?page={page_num}"
    page.goto(url, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    # 스크롤 다운하여 lazy-load 상품 로딩
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)

    soup = BeautifulSoup(page.content(), "html.parser")
    products = []

    # 상품 컨테이너 찾기: css-ioyppz 클래스 사용
    containers = soup.select("[class*='css-ioyppz']")

    if containers:
        for container in containers:
            product = parse_product_container(container)
            if product:
                products.append(product)
    else:
        # 대체: /goods/ 링크 기반 탐색
        product_links = soup.select("a[href*='/goods/']")
        seen = set()
        for link_tag in product_links:
            href = link_tag.get("href", "")
            if "/goods/" not in href:
                continue
            full_url = href if href.startswith("http") else BASE_URL + href
            if full_url in seen:
                continue
            seen.add(full_url)

            product = parse_product_from_link(link_tag, full_url)
            if product:
                products.append(product)

    return products


def parse_product_container(container) -> dict | None:
    """css-ioyppz 컨테이너에서 상품 정보를 추출합니다."""
    # 링크 찾기
    link_tag = container.select_one("a[href*='/goods/']")
    if not link_tag:
        link_tag = container.find_parent("a")
        if not link_tag or "/goods/" not in link_tag.get("href", ""):
            return None

    href = link_tag.get("href", "")
    full_url = href if href.startswith("http") else BASE_URL + href

    # 상품명: css-11hy0d7 클래스
    name = ""
    name_tag = container.select_one("[class*='css-11hy0d7']")
    if name_tag:
        name = name_tag.get_text(strip=True)
    else:
        # 대체: 컨테이너 내 텍스트에서 상품명 추출
        for tag in container.select("span, p, div"):
            text = tag.get_text(strip=True)
            if text and not re.match(r'^[\d,%원]+$', text) and len(text) > 1:
                name = text
                break

    if not name:
        return None

    # 가격 찾기
    price = extract_price(container)

    return {"name": name, "link": full_url, "price": price}


def parse_product_from_link(link_tag, full_url: str) -> dict | None:
    """<a> 태그에서 상품 정보를 추출합니다."""
    # 상품명
    name = ""
    name_tag = link_tag.select_one("[class*='css-11hy0d7']")
    if name_tag:
        name = name_tag.get_text(strip=True)
    else:
        for tag in link_tag.select("span, p, div"):
            text = tag.get_text(strip=True)
            if text and not re.match(r'^[\d,%원]+$', text) and len(text) > 1:
                name = text
                break

    if not name:
        return None

    # 가격: 상위 요소에서 탐색
    price = extract_price(link_tag)
    if not price:
        parent = link_tag
        for _ in range(5):
            if parent.parent:
                parent = parent.parent
                price = extract_price(parent)
                if price:
                    break

    return {"name": name, "link": full_url, "price": price}


def extract_price(element) -> str:
    """요소 내에서 가격 정보를 추출합니다."""
    # '원'이 포함된 텍스트 탐색
    for tag in element.find_all(["span", "div", "p"]):
        text = tag.get_text(strip=True)
        if re.match(r'^[\d,]+원$', text):
            return text

    # 숫자,숫자 패턴 (가격)
    for tag in element.find_all(["span", "div", "p"]):
        text = tag.get_text(strip=True)
        if re.match(r'^[\d,]+$', text) and len(text) >= 3:
            return text + "원"

    return ""


def save_to_csv(products: list[dict], filename: str):
    """상품 정보를 CSV로 저장합니다."""
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["상품명", "원문링크", "가격"])
        for p in products:
            writer.writerow([p["name"], p["link"], p["price"]])
    print(f"\nCSV 저장 완료: {filename} ({len(products)}개 상품)")


def main():
    print("=" * 50)
    print("  Kurly 카테고리 상품 스크래퍼")
    print("=" * 50)

    # headless 모드 선택
    while True:
        choice = input("\nHeadless 모드로 실행하시겠습니까? (y/n): ").strip().lower()
        if choice in ("y", "n"):
            break
        print("y 또는 n을 입력해주세요.")
    headless = choice == "y"

    # 페이지 수 입력
    while True:
        try:
            max_pages = int(input("수집할 페이지 수를 입력하세요 (1 이상): ").strip())
            if max_pages >= 1:
                break
            print("1 이상의 숫자를 입력해주세요.")
        except ValueError:
            print("숫자를 입력해주세요.")

    print(f"\n설정: headless={headless}, 페이지 수={max_pages}")
    print(f"대상 URL: {CATEGORY_URL}")

    all_products = []
    seen_urls = set()

    with sync_playwright() as p:
        print("\n브라우저 시작 중...")
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        for page_num in range(1, max_pages + 1):
            print(f"\n[페이지 {page_num}/{max_pages}] 수집 중...")

            try:
                products = scrape_page(page, page_num)

                # 중복 제거
                new_count = 0
                for prod in products:
                    if prod["link"] not in seen_urls:
                        seen_urls.add(prod["link"])
                        all_products.append(prod)
                        new_count += 1

                print(f"  -> {new_count}개 상품 수집 (누적: {len(all_products)}개)")

                if new_count == 0:
                    print("  [알림] 새로운 상품이 없습니다. 마지막 페이지일 수 있습니다.")

            except Exception as e:
                print(f"  [오류] 페이지 {page_num} 수집 실패: {e}")
                continue

        browser.close()
        print("\n브라우저 종료됨.")

    if all_products:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kurly_products_{timestamp}.csv"
        save_to_csv(all_products, filename)

        # 미리보기
        print("\n--- 수집 결과 미리보기 (최대 5개) ---")
        for i, prod in enumerate(all_products[:5], 1):
            print(f"{i}. {prod['name']}")
            print(f"   링크: {prod['link']}")
            print(f"   가격: {prod['price']}")
    else:
        print("\n수집된 상품이 없습니다.")


if __name__ == "__main__":
    main()
