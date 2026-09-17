import random
from typing import List, Dict, Tuple, Any, Optional
from collections import Counter
from openai import OpenAI
from .utils import execute_sql, PROMPT_PAIRWISE_VOTE_COGNITIVE_PRIOR, call_openai_with_retry

class ConfidenceSelector:
    """
    Confidence-aware SQL Selection Gate (Algorithm 5 in DeepEye-SQL).
    
    1. Execution-based clustering of revised SQL candidates.
    2. Confidence estimation based on cluster proportions.
    3. High-confidence shortcut if top cluster confidence > threshold.
    4. Low-confidence full review with:
       - Cognitive Prior (informs LLM of empirical consensus advantage)
       - Pairwise Adjudication & Win Rate (WinRate(S_i) = 1/(K-1) * sum(V(S_i, S_j)))
       - Comprehensive scoring: Score(S_i) = Conf(S_i) * WinRate(S_i)
    """
    def __init__(
        self,
        client: Optional[OpenAI] = None,
        model_name: str = "gpt-4o",
        db_path: str = "school.db",
        threshold: float = 0.6,
        top_k: int = 3,
        num_samples: int = 1,
    ):
        self.client = client
        self.model_name = model_name
        self.db_path = db_path
        self.threshold = threshold
        self.top_k = top_k
        self.num_samples = num_samples
        self.last_selection_meta: Dict[str, Any] = {}

    def select(self, candidates: List[str], question: str) -> str:
        if not candidates:
            return ""
        if len(candidates) == 1:
            return candidates[0]

        # 1. Execute and Cluster
        clusters = self._cluster_candidates(candidates)

        # 2. Sort clusters by size (descending)
        sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
        top_cluster_key = sorted_clusters[0][0]
        top_cluster_sqls = sorted_clusters[0][1]

        total_candidates = len(candidates)
        top_confidence = len(top_cluster_sqls) / total_candidates

        # 3. High-Confidence Shortcut
        if top_confidence > self.threshold:
            self.last_selection_meta = {
                "shortcut": True,
                "confidence": top_confidence,
                "winner": top_cluster_sqls[0],
                "clusters_count": len(sorted_clusters),
            }
            return top_cluster_sqls[0]

        # 4. Low-Confidence Full Review
        k = min(self.top_k, len(sorted_clusters))
        top_k_clusters = sorted_clusters[:k]

        # Candidate representations and confidences
        top_k_sqls = [c[1][0] for c in top_k_clusters]
        confidences = [len(c[1]) / total_candidates for c in top_k_clusters]
        counts = [len(c[1]) for c in top_k_clusters]

        # Perform pairwise adjudication matrix
        # votes[(i, j)] = 1 if S_i beats S_j, 0 otherwise
        votes: Dict[Tuple[int, int], int] = {}
        for i in range(k):
            for j in range(i + 1, k):
                v_ij = self._pairwise_judge(
                    question=question,
                    sql_a=top_k_sqls[i],
                    conf_a=confidences[i],
                    count_a=counts[i],
                    sql_b=top_k_sqls[j],
                    conf_b=confidences[j],
                    count_b=counts[j],
                )
                votes[(i, j)] = v_ij
                votes[(j, i)] = 1 - v_ij

        # Calculate WinRate(S_i) = 1/(K-1) * sum_{j != i} V(S_i, S_j)
        win_rates = []
        for i in range(k):
            if k > 1:
                total_wins = sum(votes.get((i, j), 0) for j in range(k) if j != i)
                win_rate = total_wins / (k - 1)
            else:
                win_rate = 1.0
            win_rates.append(win_rate)

        # Calculate Score(S_i) = Conf(S_i) * WinRate(S_i)
        scores = [conf * wr for conf, wr in zip(confidences, win_rates)]

        # Select winner: argmax Score(S_i).
        max_score = max(scores)
        if max_score > 0:
            best_idx = scores.index(max_score)
        else:
            # Fallback to candidate with highest confidence (S_1)
            best_idx = 0

        winner = top_k_sqls[best_idx]
        self.last_selection_meta = {
            "shortcut": False,
            "confidence": top_confidence,
            "winner": winner,
            "best_idx": best_idx,
            "top_k_candidates": top_k_sqls,
            "confidences": confidences,
            "win_rates": win_rates,
            "scores": scores,
        }
        return winner

    def _cluster_candidates(self, candidates: List[str]) -> Dict[str, List[str]]:
        clusters: Dict[str, List[str]] = {}
        for sql in candidates:
            result = execute_sql(self.db_path, sql)
            key = str(result)
            if key not in clusters:
                clusters[key] = []
            clusters[key].append(sql)
        return clusters

    def _pairwise_judge(
        self,
        question: str,
        sql_a: str,
        conf_a: float,
        count_a: int,
        sql_b: str,
        conf_b: float,
        count_b: int,
    ) -> int:
        """
        Adjudicates between SQL A and SQL B with Cognitive Prior.
        Returns 1 if SQL A wins, 0 if SQL B wins.
        """
        if not self.client:
            # Fallback heuristic if no LLM client: higher confidence wins
            return 1 if conf_a >= conf_b else 0

        votes_for_a = 0
        votes_for_b = 0

        for step in range(self.num_samples):
            swap = (step % 2 == 1)
            if not swap:
                prompt = PROMPT_PAIRWISE_VOTE_COGNITIVE_PRIOR.format(
                    question=question,
                    sql_a=sql_a,
                    conf_a=conf_a,
                    count_a=count_a,
                    sql_b=sql_b,
                    conf_b=conf_b,
                    count_b=count_b,
                )
                resp = call_openai_with_retry(self.client, self.model_name, prompt).strip().upper()
                if "A" in resp and "B" not in resp:
                    votes_for_a += 1
                elif "B" in resp and "A" not in resp:
                    votes_for_b += 1
                else:
                    if conf_a >= conf_b:
                        votes_for_a += 1
                    else:
                        votes_for_b += 1
            else:
                prompt = PROMPT_PAIRWISE_VOTE_COGNITIVE_PRIOR.format(
                    question=question,
                    sql_a=sql_b,
                    conf_a=conf_b,
                    count_a=count_b,
                    sql_b=sql_a,
                    conf_b=conf_a,
                    count_b=count_a,
                )
                resp = call_openai_with_retry(self.client, self.model_name, prompt).strip().upper()
                if "A" in resp and "B" not in resp:
                    votes_for_b += 1
                elif "B" in resp and "A" not in resp:
                    votes_for_a += 1
                else:
                    if conf_a >= conf_b:
                        votes_for_a += 1
                    else:
                        votes_for_b += 1

        return 1 if votes_for_a >= votes_for_b else 0
