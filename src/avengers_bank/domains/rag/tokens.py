"""Kiwi 형태소 분석으로 내용어만 뽑는다 (BM25용, 지난 RAG 레포의 규칙 그대로)"""

from functools import lru_cache

from kiwipiepy import Kiwi

KEEP = ("NN", "NR", "VV", "VA", "XR", "SL", "SN", "SH", "MAG")  # 명사·수사·동사·형용사·어근·영문·숫자·한자·부사


@lru_cache
def kiwi() -> Kiwi:
    return Kiwi()  # 처음 한 번 1초 정도 걸려서 재사용


def tokenize(text: str) -> list[str]:
    words = []
    for t in kiwi().tokenize(text or ""):
        if t.tag.startswith(KEEP) and t.tag != "NNB":  # 의존 명사(것·수) 제외
            words.append(t.form.lower() + ("다" if t.tag.startswith("V") else ""))
    return words
