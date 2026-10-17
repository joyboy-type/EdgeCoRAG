SELECT split,model_key,COUNT(*) AS n,SUM(pattern='000') AS all_three_wrong,
 SUM(s1=0 AND s2=1) AS s1_wrong_s2_correct,
 SUM(s1=0 AND s2=1 AND s1_format=0) AS s1_valid_wrong_s2_correct,
 SUM(s1=0 AND s2=1 AND gt_hash_hit=0) AS s1_wrong_s2_correct_no_gt_hash_hit,
 SUM(s1=0 AND s2=1 AND gt_hash_hit=1) AS s1_wrong_s2_correct_with_gt_hash_hit,
 SUM(s2=0) AS s2_wrong,SUM(s0=1 AND s1=0) AS s0_right_s1_wrong
 FROM triples GROUP BY split,model_key ORDER BY split,model_key;
