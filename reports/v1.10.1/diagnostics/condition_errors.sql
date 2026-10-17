SELECT split,model_key,condition,COUNT(*) AS n,SUM(correct) AS correct,
 SUM(correct=0 AND format_failure=0) AS valid_choice_wrong,SUM(format_failure) AS format_failures,
 SUM(format_failure=1 AND budget_exhausted=1) AS format_failures_budget_exhausted
 FROM condition_runs GROUP BY split,model_key,condition ORDER BY split,model_key,condition;
