"""Step 5: group many news articles about the same event into one cluster, and count independent sources.

Why: 40 outlets repeating one wire story is ONE event, not 40 confirmations. The confidence band (step 7) rewards
independent confirmation, so the count must not be inflated by copies.

Method (deterministic, no model call, explainable):
  1. headline -> a set of significant words (lower-case, outlet suffix removed, stop-words dropped, plural 's' trimmed);
  2. two headlines are "the same event" when their word sets overlap enough (Jaccard >= SAME_EVENT) AND they share
     at least MIN_SHARED words AND the articles were seen within WINDOW_HOURS of each other;
  3. a near-identical headline (Jaccard >= SYNDICATED) from another outlet is a syndicated copy: it joins the cluster
     but its outlet does not count as an independent source;
  4. independent_sources = distinct outlets among the non-syndicated articles of a cluster.

The thresholds are our own judgment, not tuned on labelled data yet (step 9 checks them against hand-labelled pairs).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

SAME_EVENT = 0.5        # Jaccard of headline word sets
SYNDICATED = 0.85       # near-identical headline = copy of the same story
MIN_SHARED = 3          # words two headlines must share, whatever the ratio
WINDOW_HOURS = 72       # an article can only join a cluster whose newest article is at most this old

STOPWORDS = frozenset("""
a an and are as at be been but by for from has have he her his how in into is it its more most new news not of on or our out
over says say said she than that the their them then there these they this those to up was we were what when where which while
who why will with would you your after about amid against also can could may might now just one two three first last year
""".split())

# two-level public suffixes we meet in news domains (anything else: last two labels)
TWO_LEVEL_SUFFIXES = frozenset({"co.uk", "org.uk", "com.au", "net.au", "co.in", "co.nz", "co.za", "com.br", "com.cn",
                                "com.sg", "com.hk", "co.jp", "com.tr", "com.mx", "com.ng", "co.ke"})

_OUTLET_SUFFIX = re.compile(r"\s+[-|–—]\s+[^-|–—]{2,40}$")


def registrable_domain(domain: str | None) -> str:
    """'www.news.bbc.co.uk' -> 'bbc.co.uk'; '' for missing."""
    if not domain:
        return ""
    labels = domain.lower().strip().strip(".").split(".")
    if labels and labels[0] == "www":
        labels = labels[1:]
    if len(labels) >= 3 and ".".join(labels[-2:]) in TWO_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else ".".join(labels)


def significant_words(title: str) -> frozenset[str]:
    """Headline -> comparable set of words."""
    t = _OUTLET_SUFFIX.sub("", title or "").lower()
    words = []
    for w in re.findall(r"[a-z0-9]+", t):
        if len(w) < 3 and not w.isdigit():
            continue
        if w in STOPWORDS:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        words.append(w)
    return frozenset(words)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class Article:
    article_id: str
    title: str
    domain: str | None
    url: str | None
    seen_at: datetime
    country: str | None = None
    query_name: str | None = None
    words: frozenset[str] = field(default=frozenset(), repr=False)
    syndicated: bool = False

    def __post_init__(self):
        if not self.words:
            self.words = significant_words(self.title)


@dataclass
class Cluster:
    cluster_id: str
    articles: list[Article] = field(default_factory=list)

    @property
    def last_seen(self) -> datetime:
        return max(a.seen_at for a in self.articles)

    @property
    def first_seen(self) -> datetime:
        return min(a.seen_at for a in self.articles)

    def domains(self) -> set[str]:
        return {registrable_domain(a.domain) for a in self.articles if a.domain}

    def independent_domains(self) -> set[str]:
        return {registrable_domain(a.domain) for a in self.articles if a.domain and not a.syndicated}

    def representative(self) -> Article:
        """The most 'central' headline (highest average similarity to the others); earliest on ties."""
        if len(self.articles) <= 2:
            return min(self.articles, key=lambda a: a.seen_at)
        def centrality(a: Article) -> float:
            return sum(jaccard(a.words, o.words) for o in self.articles if o is not a)
        return max(self.articles, key=lambda a: (round(centrality(a), 6), -a.seen_at.timestamp()))

    def summary(self) -> dict:
        rep = self.representative()
        return {
            "cluster_id": self.cluster_id,
            "representative_title": rep.title,
            "representative_url": rep.url,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "article_count": len(self.articles),
            "distinct_domains": len(self.domains()),
            "independent_sources": len(self.independent_domains()),
            "countries": sorted({a.country for a in self.articles if a.country}),
            "query_names": sorted({a.query_name for a in self.articles if a.query_name}),
        }


class Clusterer:
    """Incremental clustering: feed articles in time order; existing clusters can be preloaded."""

    def __init__(self, clusters: list[Cluster] | None = None, window_hours: int = WINDOW_HOURS,
                 same_event: float = SAME_EVENT, syndicated: float = SYNDICATED, min_shared: int = MIN_SHARED):
        self.window = timedelta(hours=window_hours)
        self.same_event, self.syndicated, self.min_shared = same_event, syndicated, min_shared
        self.clusters: dict[str, Cluster] = {}
        self._index: dict[str, set[str]] = defaultdict(set)  # word -> cluster ids (to avoid comparing with everything)
        self.touched: set[str] = set()
        self.assigned: dict[str, str] = {}                   # article_id -> cluster_id (new articles only)
        for c in clusters or []:
            self._register(c)

    def _register(self, cluster: Cluster) -> None:
        self.clusters[cluster.cluster_id] = cluster
        for a in cluster.articles:
            for w in a.words:
                self._index[w].add(cluster.cluster_id)

    def _best_cluster(self, art: Article) -> tuple[Cluster | None, float, Article | None]:
        votes: dict[str, int] = defaultdict(int)
        for w in art.words:
            for cid in self._index.get(w, ()):
                votes[cid] += 1
        best, best_sim, best_match = None, 0.0, None
        for cid, shared_words in votes.items():
            if shared_words < self.min_shared:
                continue
            cluster = self.clusters[cid]
            if art.seen_at - cluster.last_seen > self.window:
                continue
            for member in cluster.articles:
                if len(art.words & member.words) < self.min_shared:
                    continue
                sim = jaccard(art.words, member.words)
                if sim > best_sim:
                    best, best_sim, best_match = cluster, sim, member
        if best is not None and best_sim >= self.same_event:
            return best, best_sim, best_match
        return None, best_sim, None

    def add(self, art: Article) -> str:
        cluster, sim, match = self._best_cluster(art)
        if cluster is None:
            cluster = Cluster(cluster_id=art.article_id)
            self._register(cluster)
        else:
            # near-identical headline = syndicated copy (another outlet, or the same outlet repeating itself):
            # it joins the cluster but does not count as an independent confirmation
            if sim >= self.syndicated:
                art.syndicated = True
        cluster.articles.append(art)
        for w in art.words:
            self._index[w].add(cluster.cluster_id)
        self.touched.add(cluster.cluster_id)
        self.assigned[art.article_id] = cluster.cluster_id
        return cluster.cluster_id


def cluster_articles(articles: list[Article], **kwargs) -> list[Cluster]:
    """Convenience for tests/offline use: cluster a list of articles (any order)."""
    c = Clusterer(**kwargs)
    for art in sorted(articles, key=lambda a: a.seen_at):
        c.add(art)
    return list(c.clusters.values())
