#!/usr/bin/env python3
"""抓取质量检查 + 同源去重。

用法：
  python3 quality_checks.py page.txt --title-keyword PaperBenchX
  python3 quality_checks.py --dedupe a.txt b.txt c.txt

规则（任一不满足即判为抓取失败）：
  1. 正文长度 < 800 字符
  2. 标题关键词在正文中命中 0 次
  3. 出现污染短语
同源去重：任意两篇的 5-gram 字符集合 Jaccard 相似度 ≥ 0.5，视为同一篇 PR 的转载。
"""
import argparse, itertools, re, sys

POLLUTION = ["浏览器版本过旧", "环境异常", "扫码下载", "请在微信客户端打开", "登录后查看",
             "enable JavaScript", "Access Denied", "verify you are human"]

def check(text, keyword=None, min_len=800):
    body = re.sub(r"\s+", "", text)
    problems = []
    if len(body) < min_len:
        problems.append(f"正文过短（{len(body)} < {min_len}）")
    if keyword and keyword.lower() not in text.lower():
        problems.append(f"标题关键词未命中：{keyword}")
    hits = [p for p in POLLUTION if p.lower() in text.lower()]
    if hits:
        problems.append("出现污染短语：" + "、".join(hits))
    return problems

def shingles(text, n=5):
    s = re.sub(r"\s+", "", text)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}

def dedupe(paths, threshold=0.5):
    sets = {p: shingles(open(p, encoding="utf-8").read()) for p in paths}
    pairs = []
    for a, b in itertools.combinations(paths, 2):
        sa, sb = sets[a], sets[b]
        if sa and sb:
            j = len(sa & sb) / len(sa | sb)
            if j >= threshold:
                pairs.append((a, b, round(j, 2)))
    return pairs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--title-keyword")
    ap.add_argument("--min-len", type=int, default=800)
    ap.add_argument("--dedupe", action="store_true")
    a = ap.parse_args()
    if a.dedupe:
        pairs = dedupe(a.files)
        for x, y, j in pairs:
            print(f"同源：{x} ≈ {y}（Jaccard {j}）")
        if not pairs:
            print("未发现同源转载")
        return
    bad = 0
    for f in a.files:
        probs = check(open(f, encoding="utf-8").read(), a.title_keyword, a.min_len)
        print(f"{'✗' if probs else '✓'} {f}" + (": " + "；".join(probs) if probs else ""))
        bad += bool(probs)
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
