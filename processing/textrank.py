"""
textrank.py — Graph-based TextRank algorithm for extractive summarization.
Ranks sentences by centrality in a similarity graph, finding sentences that
are most representative of the overall discussion.
"""

import re
import math
from collections import Counter
from typing import List, Dict, Tuple


# Stop words for TF-IDF
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "don", "now", "and", "but", "or", "if", "while", "this", "that",
    "these", "those", "i", "me", "my", "we", "our", "you", "your", "he",
    "him", "his", "she", "her", "it", "its", "they", "them", "their",
    "what", "which", "who", "whom", "am", "up", "about",
}


def _tokenize(text: str) -> List[str]:
    """Split text into lowercase word tokens, filtering stop words."""
    words = re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def _compute_tfidf(sentences: List[str]) -> List[Dict[str, float]]:
    """Compute TF-IDF vectors for each sentence."""
    # Term frequency per sentence
    tf_vectors = []
    for sent in sentences:
        words = _tokenize(sent)
        counter = Counter(words)
        total = max(len(words), 1)
        tf_vectors.append({w: c / total for w, c in counter.items()})

    # Document frequency
    df = Counter()
    for tf in tf_vectors:
        for word in tf:
            df[word] += 1

    n_docs = max(len(sentences), 1)

    # TF-IDF
    tfidf_vectors = []
    for tf in tf_vectors:
        tfidf = {}
        for word, tf_val in tf.items():
            idf = math.log(n_docs / max(df[word], 1)) + 1
            tfidf[word] = tf_val * idf
        tfidf_vectors.append(tfidf)

    return tfidf_vectors


def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    if not vec_a or not vec_b:
        return 0.0

    # Intersection
    common_words = set(vec_a.keys()) & set(vec_b.keys())
    if not common_words:
        return 0.0

    dot_product = sum(vec_a[w] * vec_b[w] for w in common_words)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot_product / (mag_a * mag_b)


def textrank_sentences(
    sentences: List[str],
    damping: float = 0.85,
    max_iterations: int = 100,
    convergence_threshold: float = 0.0001,
) -> List[Tuple[int, float]]:
    """
    Rank sentences using the TextRank algorithm.

    Args:
        sentences: List of sentence strings
        damping: Damping factor (default 0.85)
        max_iterations: Maximum iterations
        convergence_threshold: Stop when scores change less than this

    Returns:
        List of (sentence_index, score) sorted by score descending
    """
    n = len(sentences)
    if n == 0:
        return []
    if n == 1:
        return [(0, 1.0)]

    # Build TF-IDF vectors
    tfidf_vectors = _compute_tfidf(sentences)

    # Build similarity matrix
    similarity = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(tfidf_vectors[i], tfidf_vectors[j])
            similarity[i][j] = sim
            similarity[j][i] = sim

    # Compute outgoing weights for normalization
    out_weights = [sum(similarity[i]) for i in range(n)]

    # Initialize scores uniformly
    scores = [1.0 / n] * n

    # Iterate until convergence
    for iteration in range(max_iterations):
        new_scores = [0.0] * n
        max_delta = 0.0

        for i in range(n):
            rank_sum = 0.0
            for j in range(n):
                if j != i and out_weights[j] > 0:
                    rank_sum += similarity[j][i] * scores[j] / out_weights[j]

            new_scores[i] = (1 - damping) / n + damping * rank_sum
            max_delta = max(max_delta, abs(new_scores[i] - scores[i]))

        scores = new_scores

        if max_delta < convergence_threshold:
            break

    # Return sorted by score
    indexed_scores = list(enumerate(scores))
    indexed_scores.sort(key=lambda x: x[1], reverse=True)
    return indexed_scores


def select_top_sentences(
    sentences: List[str],
    top_n: int = 8,
    diversity_threshold: float = 0.7,
) -> List[str]:
    """
    Select top N sentences using TextRank with diversity filtering.
    Re-orders selected sentences by their original position for coherence.
    """
    if not sentences:
        return []

    ranked = textrank_sentences(sentences)
    tfidf_vectors = _compute_tfidf(sentences)

    selected_indices = []
    for idx, score in ranked:
        if len(selected_indices) >= top_n:
            break

        # Diversity check: skip if too similar to already selected
        is_diverse = True
        for sel_idx in selected_indices:
            sim = _cosine_similarity(tfidf_vectors[idx], tfidf_vectors[sel_idx])
            if sim > diversity_threshold:
                is_diverse = False
                break

        if is_diverse:
            selected_indices.append(idx)

    # Re-order by original position for coherence
    selected_indices.sort()

    return [sentences[i] for i in selected_indices]
