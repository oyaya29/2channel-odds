"""
オッズ計算モジュール
競馬式オッズ（出現数が多いほど低オッズ）を計算
同義語グループ対応
"""
import re
from typing import List, Dict, Union


def parse_keyword_groups(keywords_raw: List[str]) -> List[dict]:
    """
    キーワードリストを同義語グループに変換

    Args:
        keywords_raw: キーワードリスト（'|'区切りで同義語を指定可能）
                     例: ['Aチーム|A|チームA', 'Bチーム', 'Cチーム|C']

    Returns:
        [{'display': '表示名', 'synonyms': ['同義語リスト']}] のリスト
    """
    groups = []
    for kw in keywords_raw:
        if '|' in kw:
            synonyms = [s.strip() for s in kw.split('|') if s.strip()]
            if synonyms:
                groups.append({
                    'display': synonyms[0],  # 最初の語を表示名にする
                    'synonyms': synonyms
                })
        else:
            groups.append({
                'display': kw,
                'synonyms': [kw]
            })
    return groups


def count_keyword_groups(posts: List[str], keyword_groups: List[dict]) -> Dict[str, int]:
    """
    レス本文リストから各キーワードグループの出現回数をカウント

    - レス単位でカウント：1つのレス内で同義語のどれかが1回でも出現すれば1カウント
    - 同じレス内で同じ同義語が複数回出現しても1カウント
    - 長い語が短い語を含む場合も、そのレスは1カウント

    Args:
        posts: レス本文のリスト
        keyword_groups: キーワードグループのリスト

    Returns:
        {表示名: 出現数} の辞書
    """
    counts = {g['display']: 0 for g in keyword_groups}

    for group in keyword_groups:
        # 同義語を長さの降順でソート（長いものを先にマッチさせる）
        synonyms_sorted = sorted(group['synonyms'], key=len, reverse=True)

        # 正規表現パターンを作成（長い語を先に配置してOR結合）
        pattern_parts = [re.escape(s.lower()) for s in synonyms_sorted]
        pattern = '(' + '|'.join(pattern_parts) + ')'

        # 各レスで同義語のどれかが出現しているかチェック
        for post in posts:
            post_lower = post.lower()
            if re.search(pattern, post_lower):
                counts[group['display']] += 1

    return counts


def count_keywords(posts: List[str], keywords: List[str]) -> Dict[str, int]:
    """
    レス本文リストから各キーワードの出現回数をカウント（後方互換性用）

    Args:
        posts: レス本文のリスト
        keywords: 検索するキーワードのリスト

    Returns:
        {キーワード: 出現数} の辞書
    """
    groups = parse_keyword_groups(keywords)
    return count_keyword_groups(posts, groups)


def calculate_odds(counts: Dict[str, int], payout_rate: float = 0.80) -> Dict[str, dict]:
    """
    競馬式オッズを計算

    計算式:
        オッズ = (全キーワード出現合計 × 払い戻し率) / 該当キーワード出現数

    Args:
        counts: {キーワード: 出現数} の辞書
        payout_rate: 払い戻し率（0.0〜1.0、デフォルト0.80=80%）

    Returns:
        {キーワード: {'count': 出現数, 'odds': オッズ, 'probability': 確率}} の辞書
    """
    total_count = sum(counts.values())

    results = {}

    for keyword, count in counts.items():
        if count == 0:
            # 出現数0の場合
            results[keyword] = {
                'count': 0,
                'odds': None,  # 計算不能
                'odds_display': '-',
                'probability': 0.0,
                'probability_display': '0.0%'
            }
        else:
            # オッズ計算: (合計 × 払い戻し率) / 出現数
            odds = (total_count * payout_rate) / count

            # 最小オッズは1.0
            odds = max(odds, 1.0)

            # 確率（出現数 / 合計）
            probability = count / total_count if total_count > 0 else 0

            results[keyword] = {
                'count': count,
                'odds': odds,
                'odds_display': f'{odds:.2f}',
                'probability': probability,
                'probability_display': f'{probability * 100:.1f}%'
            }

    return results


def analyze_thread(posts: List[str], keywords: List[str], payout_rate: float = 0.80) -> dict:
    """
    スレッドを分析してオッズを計算

    Args:
        posts: レス本文のリスト
        keywords: 検索するキーワードのリスト（'|'で同義語を指定可能）
        payout_rate: 払い戻し率（0.0〜1.0）

    Returns:
        分析結果の辞書
    """
    # キーワードグループを解析
    keyword_groups = parse_keyword_groups(keywords)

    # キーワード出現数をカウント
    counts = count_keyword_groups(posts, keyword_groups)

    # オッズを計算
    odds_results = calculate_odds(counts, payout_rate)

    # 合計出現数
    total_count = sum(counts.values())

    # オッズの低い順（人気順）でソート
    sorted_results = dict(
        sorted(
            odds_results.items(),
            key=lambda x: (x[1]['odds'] is None, x[1]['odds'] if x[1]['odds'] else float('inf'))
        )
    )

    # 同義語情報を追加
    synonym_info = {g['display']: g['synonyms'] for g in keyword_groups}

    return {
        'results': sorted_results,
        'total_count': total_count,
        'post_count': len(posts),
        'payout_rate': payout_rate,
        'keywords': keywords,
        'synonym_info': synonym_info
    }


if __name__ == "__main__":
    # テスト1: 基本的な同義語グループ（レス単位カウント）
    print("=== テスト1: 基本的な同義語（レス単位） ===")
    test_posts1 = [
        "Aチームは強いと思う",      # Aチーム: 1カウント
        "Bチームが勝つでしょう",    # Bチーム: 1カウント
        "やっぱりAだな",            # Aチーム: 1カウント
        "Cチームも侮れない",        # Cチーム: 1カウント
        "Aで間違いない",            # Aチーム: 1カウント
        "Bの調子がいい",            # Bチーム: 1カウント
        "チームAしかない",          # Aチーム: 1カウント
        "A最強",                    # Aチーム: 1カウント
    ]
    test_keywords1 = ["Aチーム|A|チームA", "Bチーム|B", "Cチーム|C", "Dチーム"]
    result1 = analyze_thread(test_posts1, test_keywords1, 0.80)

    print(f"分析レス数: {result1['post_count']}")
    print(f"キーワード出現合計: {result1['total_count']}")
    print("期待: Aチーム=5, Bチーム=2, Cチーム=1")
    for keyword, data in result1['results'].items():
        synonyms = result1['synonym_info'].get(keyword, [keyword])
        syn_str = f" (同義語: {', '.join(synonyms)})" if len(synonyms) > 1 else ""
        print(f"  {keyword}{syn_str}: {data['count']}回")

    # テスト2: 同一レス内で複数回出現しても1カウント
    print("\n=== テスト2: 同一レス内複数回 → 1カウント ===")
    test_posts2 = [
        "エンペラーワケア最強！エンペラーワケア頑張れ！",  # 1カウント
        "エンペラーも侮れない",                            # 1カウント
        "やっぱりエンペラーワケアだな",                    # 1カウント
        "他の馬も良い",                                    # 他の馬: 1カウント
    ]
    test_keywords2 = ["エンペラーワケア|エンペラー", "他の馬"]
    result2 = analyze_thread(test_posts2, test_keywords2, 0.80)

    print(f"分析レス数: {result2['post_count']}")
    print(f"キーワード出現合計: {result2['total_count']}")
    print("期待: エンペラーワケア=3（レス数）, 他の馬=1")
    for keyword, data in result2['results'].items():
        synonyms = result2['synonym_info'].get(keyword, [keyword])
        syn_str = f" (同義語: {', '.join(synonyms)})" if len(synonyms) > 1 else ""
        print(f"  {keyword}{syn_str}: {data['count']}回")
