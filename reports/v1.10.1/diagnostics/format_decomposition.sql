SELECT split,model_key,left_condition,right_condition,
 CASE WHEN left_format=1 AND right_format=1 THEN 'both_format_failure'
      WHEN left_format=1 THEN 'left_only_format_failure'
      WHEN right_format=1 THEN 'right_only_format_failure'
      ELSE 'both_parse_ok' END AS format_group,
 COUNT(*) AS n,SUM(right_correct-left_correct) AS net_correct_change,
 SUM(left_correct=0 AND right_correct=1) AS improvements,
 SUM(left_correct=1 AND right_correct=0) AS regressions
 FROM contrasts GROUP BY split,model_key,left_condition,right_condition,format_group
 ORDER BY split,model_key,left_condition,right_condition,format_group;
