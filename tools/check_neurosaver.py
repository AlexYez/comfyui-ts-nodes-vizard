"""Audit every compiled article and curated link; never claim manual relevance approval."""
from concurrent.futures import ThreadPoolExecutor
import catalog as c
from editorial_catalog_check import check_link


def main():
    reading = c.load_json(c.CONTENT / "related-reading.json")
    compiled, _ = c.compile_catalog()
    _, articles, _, _ = c.load_source_catalog()
    rows = []
    for _, m in articles:
        selected = c.select_related_reading(m, reading)
        body = next(x["body"] for x in compiled["articles"] if x["manifest"]["articleId"] == m["articleId"])
        assert selected["url"] in body and "https://neurosaver.ru/" in body
        assert body.count("## Связанные материалы") == 1
        rows.append({"articleId": m["articleId"], "url": selected["url"], "context": selected["context"], "generalIntroduction": selected == reading["fallback"], "selection": "curated topic rule; not individual human approval"})
    urls = sorted({x["url"] for x in [reading["fallback"], *reading["rules"], *reading.get("specificRules", []), *reading["common"]]})
    with ThreadPoolExecutor(max_workers=8) as pool:
        links = [{**x, "checkedAt": "2026-11-14"} for x in pool.map(check_link, urls)]
    c.write_json(c.CONTENT / "research/neurosaver-2026-11-14.json", {"checkedThrough": "2026-11-14", "articleCount": len(rows), "generalIntroductions": sum(r["generalIntroduction"] for r in rows), "articles": rows, "links": links})
    print("Articles", len(rows), "links", len(links), "failed", sum(x.get("status") != 200 for x in links))


if __name__ == "__main__":
    main()
