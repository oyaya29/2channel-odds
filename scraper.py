"""
5ちゃんねる スクレイピングモジュール
"""
import re
import time
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup


# User-Agent（Monazilla形式）
USER_AGENT = "Monazilla/1.00 (2chOdds/1.0)"

# リクエスト間隔（秒）
REQUEST_INTERVAL = 1.0


def parse_thread_url(url: str) -> dict:
    """
    5chスレッドURLを解析してホスト名、板名、スレッドIDを抽出

    対応URL形式:
    - https://[host].5ch.net/test/read.cgi/[board]/[thread_id]/
    - https://[host].5ch.net/test/read.cgi/[board]/[thread_id]
    - https://[host].2ch.sc/test/read.cgi/[board]/[thread_id]/
    - https://itest.5ch.net/[host]/test/read.cgi/[board]/[thread_id]/
    """
    parsed = urlparse(url)
    host = parsed.netloc

    # itest.5ch.net形式（スマホ版URL）を変換
    # https://itest.5ch.net/lavender/test/read.cgi/keiba/xxx/
    # → host=lavender.5ch.net, path=/test/read.cgi/keiba/xxx/
    if host == 'itest.5ch.net':
        itest_match = re.match(r'/([^/]+)/test/read\.cgi/([^/]+)/(\d+)', parsed.path)
        if itest_match:
            real_host = f"{itest_match.group(1)}.5ch.net"
            return {
                'host': real_host,
                'board': itest_match.group(2),
                'thread_id': itest_match.group(3),
                'base_url': f"{parsed.scheme}://{real_host}"
            }

    # read.cgi形式のパスを解析
    match = re.match(r'/test/read\.cgi/([^/]+)/(\d+)', parsed.path)
    if match:
        return {
            'host': host,
            'board': match.group(1),
            'thread_id': match.group(2),
            'base_url': f"{parsed.scheme}://{host}"
        }

    raise ValueError(f"無効なスレッドURL形式: {url}")


def fetch_thread_dat(host: str, board: str, thread_id: str, base_url: str) -> str:
    """
    dat形式でスレッドを取得（高速・効率的）
    """
    dat_url = f"{base_url}/{board}/dat/{thread_id}.dat"

    headers = {
        'User-Agent': USER_AGENT,
        'Accept-Encoding': 'gzip',
    }

    response = requests.get(dat_url, headers=headers, timeout=30)

    if response.status_code == 200:
        # Shift-JISでデコード
        try:
            return response.content.decode('cp932')
        except UnicodeDecodeError:
            return response.content.decode('shift_jis', errors='replace')

    return None


def fetch_thread_html(url: str) -> str:
    """
    HTML形式でスレッドを取得（フォールバック用）
    """
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
    }

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code == 200:
        # エンコーディング検出
        if response.encoding is None or response.encoding == 'ISO-8859-1':
            try:
                return response.content.decode('cp932')
            except UnicodeDecodeError:
                return response.content.decode('shift_jis', errors='replace')
        return response.text

    raise Exception(f"スレッドの取得に失敗しました (HTTP {response.status_code})")


def parse_dat_content(dat_content: str) -> list:
    """
    dat形式のコンテンツを解析してレス本文のリストを返す

    dat形式: 名前<>メール<>日付ID<>本文<>スレタイ（1レス目のみ）
    """
    posts = []
    lines = dat_content.strip().split('\n')

    for line in lines:
        parts = line.split('<>')
        if len(parts) >= 4:
            # 本文は4番目の要素（インデックス3）
            body = parts[3]
            # HTMLタグを除去
            body = re.sub(r'<br>', '\n', body)
            body = re.sub(r'<[^>]+>', '', body)
            # HTMLエンティティをデコード
            body = body.replace('&gt;', '>').replace('&lt;', '<')
            body = body.replace('&amp;', '&').replace('&quot;', '"')
            posts.append(body.strip())

    return posts


def parse_html_content(html_content: str) -> list:
    """
    HTML形式のコンテンツを解析してレス本文のリストを返す
    """
    soup = BeautifulSoup(html_content, 'lxml')
    posts = []

    # 5ch の投稿本文を取得（複数のセレクタを試行）
    selectors = [
        'div.message',
        'dd.thread_in',
        'div.post-content',
        'article.post div.message',
        'div.res div.message',
    ]

    for selector in selectors:
        messages = soup.select(selector)
        if messages:
            for msg in messages:
                text = msg.get_text(separator='\n', strip=True)
                if text:
                    posts.append(text)
            break

    # フォールバック: postクラスを持つ要素を探す
    if not posts:
        for post in soup.find_all(class_=re.compile(r'post|res|comment')):
            # 本文部分を探す
            body = post.find(class_=re.compile(r'message|body|content'))
            if body:
                text = body.get_text(separator='\n', strip=True)
                if text:
                    posts.append(text)

    return posts


def scrape_thread(url: str) -> dict:
    """
    5chスレッドをスクレイピングしてレス一覧を取得

    Args:
        url: 5chスレッドURL

    Returns:
        dict: {
            'posts': レス本文のリスト,
            'post_count': レス数,
            'url': 元URL
        }
    """
    # URL解析
    try:
        thread_info = parse_thread_url(url)
    except ValueError as e:
        raise Exception(str(e))

    posts = []

    # dat形式で取得を試行
    dat_content = fetch_thread_dat(
        thread_info['host'],
        thread_info['board'],
        thread_info['thread_id'],
        thread_info['base_url']
    )

    if dat_content:
        posts = parse_dat_content(dat_content)

    # dat形式が失敗した場合、HTML形式でフォールバック
    if not posts:
        time.sleep(REQUEST_INTERVAL)  # レート制限対策
        html_content = fetch_thread_html(url)
        posts = parse_html_content(html_content)

    if not posts:
        raise Exception("レスの取得に失敗しました。URLを確認してください。")

    return {
        'posts': posts,
        'post_count': len(posts),
        'url': url
    }


if __name__ == "__main__":
    # テスト用
    import sys
    if len(sys.argv) > 1:
        result = scrape_thread(sys.argv[1])
        print(f"取得レス数: {result['post_count']}")
        for i, post in enumerate(result['posts'][:5], 1):
            print(f"\n--- レス {i} ---")
            print(post[:200] + "..." if len(post) > 200 else post)
