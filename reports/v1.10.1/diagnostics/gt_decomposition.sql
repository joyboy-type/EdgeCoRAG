SELECT split,model_key,gt_hash_hit,COUNT(*) AS n,
 SUM(s1-s0) AS net_correct_change,SUM(s0=0 AND s1=1) AS improvements,
 SUM(s0=1 AND s1=0) AS regressions,
 SUM(s1=0 AND s2=1) AS s1_wrong_s2_correct,
 SUM(s1=0 AND s2=1 AND s1_format=0) AS s1_valid_wrong_s2_correct
 FROM triples GROUP BY split,model_key,gt_hash_hit ORDER BY split,model_key,gt_hash_hit;
