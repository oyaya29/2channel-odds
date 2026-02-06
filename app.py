"""
2ちゃんねるオッズ作成システム - Flask Webアプリケーション
"""
import re
from flask import Flask, render_template, request, jsonify
from scraper import scrape_thread
from odds_calculator import analyze_thread

app = Flask(__name__)


def parse_url_line(line: str) -> dict:
    """
    URL行をパースしてURLとレス番号範囲を抽出

    形式:
    - "URL" → 全レス
    - "URL 開始" → 開始番号から最後まで
    - "URL 開始-終了" → 開始番号から終了番号まで

    例:
    - "https://xxx.5ch.net/..." → {'url': '...', 'start': 1, 'end': None}
    - "https://xxx.5ch.net/... 50" → {'url': '...', 'start': 50, 'end': None}
    - "https://xxx.5ch.net/... 1-100" → {'url': '...', 'start': 1, 'end': 100}
    """
    line = line.strip()
    if not line:
        return None

    # URLとレス番号範囲を分離（スペースまたはタブで区切る）
    parts = re.split(r'\s+', line)

    url = parts[0]
    start_num = 1
    end_num = None

    if len(parts) >= 2:
        range_str = parts[1]
        if '-' in range_str:
            # "開始-終了" 形式
            range_parts = range_str.split('-')
            try:
                start_num = int(range_parts[0]) if range_parts[0] else 1
                end_num = int(range_parts[1]) if range_parts[1] else None
            except ValueError:
                pass
        else:
            # "開始" のみ
            try:
                start_num = int(range_str)
            except ValueError:
                pass

    # バリデーション
    if start_num < 1:
        start_num = 1
    if end_num is not None and end_num < start_num:
        end_num = None  # 無効な範囲は無視

    return {
        'url': url,
        'start': start_num,
        'end': end_num
    }


@app.route('/', methods=['GET'])
def index():
    """メインページを表示"""
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    """スレッドを分析してオッズを計算（複数URL対応・スレッドごとのレス番号範囲指定）"""
    try:
        # フォームデータを取得
        urls_raw = request.form.get('urls', '').strip()
        keywords_raw = request.form.get('keywords', '').strip()
        payout_rate = float(request.form.get('payout_rate', 80)) / 100

        # URL行をパース（スレッドごとのレス番号範囲付き）
        url_entries = []
        for line in urls_raw.split('\n'):
            entry = parse_url_line(line)
            if entry:
                url_entries.append(entry)

        # バリデーション
        if not url_entries:
            return jsonify({'error': 'スレッドURLを入力してください'}), 400

        if not keywords_raw:
            return jsonify({'error': 'キーワードを入力してください'}), 400

        # キーワードをパース（カンマまたは改行区切り）
        keywords = [
            kw.strip()
            for kw in keywords_raw.replace('\n', ',').split(',')
            if kw.strip()
        ]

        if len(keywords) < 2:
            return jsonify({'error': 'キーワードは2つ以上入力してください'}), 400

        # 払い戻し率の範囲チェック
        if not (0.1 <= payout_rate <= 1.0):
            return jsonify({'error': '払い戻し率は10%〜100%の範囲で指定してください'}), 400

        # 複数スレッドをスクレイピング
        all_posts = []
        thread_results = []

        for entry in url_entries:
            url = entry['url']
            start_num = entry['start']
            end_num = entry['end']

            try:
                thread_data = scrape_thread(url)
                posts = thread_data['posts']
                total_posts = len(posts)

                # レス番号範囲でフィルタリング（1-indexed）
                slice_start = start_num - 1
                slice_end = end_num if end_num else total_posts

                filtered_posts = posts[slice_start:slice_end]

                all_posts.extend(filtered_posts)
                thread_results.append({
                    'url': url,
                    'post_count': len(filtered_posts),
                    'total_posts': total_posts,
                    'range': f"{start_num}-{end_num if end_num else total_posts}",
                    'status': 'success'
                })
            except Exception as e:
                thread_results.append({
                    'url': url,
                    'post_count': 0,
                    'status': 'error',
                    'error': str(e)
                })

        if not all_posts:
            return jsonify({'error': '有効なスレッドからレスを取得できませんでした'}), 400

        # オッズを計算
        analysis = analyze_thread(
            all_posts,
            keywords,
            payout_rate
        )

        # 同義語情報を取得
        synonym_info = analysis.get('synonym_info', {})

        # レスポンス
        return jsonify({
            'success': True,
            'results': [
                {
                    'keyword': kw,
                    'count': data['count'],
                    'odds': data['odds_display'],
                    'probability': data['probability_display'],
                    'synonyms': synonym_info.get(kw, [kw])
                }
                for kw, data in analysis['results'].items()
            ],
            'summary': {
                'total_count': analysis['total_count'],
                'post_count': analysis['post_count'],
                'payout_rate': f"{analysis['payout_rate'] * 100:.0f}%",
                'keyword_count': len(keywords),
                'thread_count': len(url_entries),
                'success_count': sum(1 for t in thread_results if t['status'] == 'success')
            },
            'threads': thread_results
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
